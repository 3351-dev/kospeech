"""
Copyright 2020- Kai.Lib

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import random
import torch
import torch.nn as nn
import torch.nn.functional as F

from models.beam import Beam
from .attention import Attention

if torch.cuda.is_available():
    import torch.cuda as device
else:
    import torch as device


class Speller(nn.Module):
    """
    Converts higher level features (from listener) into output utterances by specifying a probability distribution over sequences of characters.

    Parameters
    ------------
        - **vocab_size** (int): size of the vocabulary
        - **max_len** (int): a maximum allowed length for the sequence to be processed
        - **hidden_size** (int): the number of features in the hidden state `h`
        - **sos_id** (int): index of the start of sentence symbol
        - **eos_id** (int): index of the end of sentence symbol
        - **layer_size** (int, optional): number of recurrent layers (default: 1)
        - **rnn_cell** (str, optional): type of RNN cell (default: gru)
        - **dropout_p** (float, optional): dropout probability for the output sequence (default: 0)
        - **use_attention** (bool, optional): flag indication whether to use attention mechanism or not (default: false)
        - **k** (int) : size of beam

    Inputs
    --------
        - **inputs** (batch, seq_len, input_size): list of sequences, whose length is the batch size and within which
          each sequence is a list of token IDs.  It is used for teacher forcing when provided. (default `None`)
        - **listener_hidden** (num_layers * num_directions, batch_size, hidden_size): tensor containing the features in the
          hidden state `h` of listener. Used as the initial hidden state of the decoder. (default `None`)
        - **listener_outputs** (batch, seq_len, hidden_size): tensor with containing the outputs of the listener.
          Used for attention mechanism (default is `None`).
        - **function** (torch.nn.Module): A function used to generate symbols from RNN hidden state
          (default is `torch.nn.functional.log_softmax`).
        - **teacher_forcing_ratio** (float): The probability that teacher forcing will be used. A random number is
          drawn uniformly from 0-1 for every decoding token, and if the sample is smaller than the given value,
          teacher forcing would be used (default is 0).

    Returns
    ---------
        - **speller_outputs** (seq_len, batch, vocab_size): list of tensors with size (batch_size, vocab_size) containing the outputs of the decoding function.

    Reference
    -----------
        「Listen, Attend and Spell」 paper
         https://arxiv.org/abs/1508.01211
    """

    def __init__(self, vocab_size, max_len, hidden_size,
                 sos_id, eos_id, layer_size=1, rnn_cell='gru',
                 dropout_p=0, use_attention=True, device=None, k=8):
        super(Speller, self).__init__()
        assert rnn_cell.lower() == 'lstm' or rnn_cell.lower() == 'gru' or rnn_cell.lower() == 'rnn'
        self.rnn_cell = nn.LSTM if rnn_cell.lower() == 'lstm' else nn.GRU if rnn_cell.lower() == 'gru' else nn.RNN
        self.device = device
        self.rnn = self.rnn_cell(hidden_size , hidden_size, layer_size, batch_first=True, dropout=dropout_p).to(self.device)
        self.output_size = vocab_size
        self.max_len = max_len
        self.use_attention = use_attention
        self.eos_id = eos_id
        self.sos_id = sos_id
        self.hidden_size = hidden_size
        self.embedding = nn.Embedding(self.output_size, self.hidden_size)
        self.layer_size = layer_size
        self.input_dropout = nn.Dropout(p=dropout_p)
        self.k = k
        if use_attention:
            self.attention = Attention(decoder_hidden_size=hidden_size)
        self.out = nn.Linear(self.hidden_size, self.output_size)

    def _forward_step(self, input, speller_hidden, listener_outputs, function):
        """ forward one time step """
        batch_size = input.size(0)
        output_size = input.size(1)
        embedded = self.embedding(input).to(self.device)
        embedded = self.input_dropout(embedded)

        if self.training:
            self.rnn.flatten_parameters()
        speller_output = self.rnn(embedded, speller_hidden)[0]

        if self.use_attention:
            context = self.attention(speller_output, listener_outputs)
        else:
            context = speller_output

        predicted_softmax = function(self.out(context.contiguous().view(-1, self.hidden_size)), dim=1).view(batch_size, output_size, -1)
        return predicted_softmax

    def forward(self, inputs, listener_hidden, listener_outputs, function=F.log_softmax, teacher_forcing_ratio=0.99, use_beam_search=False):
        y_hats, logit = None, None
        decode_results = []
        batch_size = inputs.size(0)
        max_len = inputs.size(1) - 1  # minus the start of sequence symbol
        speller_hidden = torch.FloatTensor(self.layer_size, batch_size, self.hidden_size).uniform_(-0.1, 0.1).to(self.device)
        use_teacher_forcing = True if random.random() < teacher_forcing_ratio else False

        if use_beam_search:
            """ Beam-Search Decoding """
            inputs = inputs[:, 0].unsqueeze(1)
            beam = Beam(
                k = self.k,
                decoder_hidden = speller_hidden,
                decoder = self,
                batch_size = batch_size,
                max_len = max_len,
                function = function
            )
            y_hats = beam.search(inputs, listener_outputs)
        else:
            if use_teacher_forcing:
                """ if teacher_forcing, Infer all at once """
                inputs = inputs[:, :-1]
                predicted_softmax = self._forward_step(
                    input = inputs,
                    speller_hidden = speller_hidden,
                    listener_outputs = listener_outputs,
                    function = function
                )
                for di in range(predicted_softmax.size(1)):
                    step_output = predicted_softmax[:, di, :]
                    decode_results.append(step_output)
            else:
                input = inputs[:, 0].unsqueeze(1)
                for di in range(max_len):
                    predicted_softmax = self._forward_step(
                        input = input,
                        speller_hidden = speller_hidden,
                        listener_outputs = listener_outputs,
                        function = function
                    )
                    step_output = predicted_softmax.squeeze(1)
                    decode_results.append(step_output)
                    input = decode_results[-1].topk(1)[1]

            logit = torch.stack(decode_results, dim=1).to(self.device)
            y_hats = logit.max(-1)[1]
        return y_hats, logit