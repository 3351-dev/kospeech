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

import Levenshtein as Lev
from utils.label import label_to_string

def char_distance(target, y_hat):
    """
    Calculating charater distance between target & y_hat

    Parameters
    -----------
        - **target**: sequence of target
        - **y_hat**: sequence of y_Hat

    Result
    --------
        - **distance**: distance between target & y_hat
        - **length**: length of target sequence
    """
    target = target.replace(' ', '')
    y_hat = y_hat.replace(' ', '')
    distance = Lev.distance(y_hat, target)
    length = len(target.replace(' ', ''))

    return distance, length

def get_distance(targets, y_hats, id2char, eos_id):
    """
    Provides total character distance between targets & y_hats

    Parameters
    -----------
        - **targets**: set of target
        - **y_hats**: set of y_hat
        - **id2char**: id2char[id] = ch
        - **eos_id**: identification of <end of sequence>

    Returns
    --------
        - **total_distance**: total distance between targets & y_hats
        - **total_length**: total length of targets sequence
    """
    total_distance = 0
    total_length = 0

    for i in range(len(targets)):
        target = label_to_string(targets[i], id2char, eos_id)
        y_hat = label_to_string(y_hats[i], id2char, eos_id)
        distance, length = char_distance(target, y_hat)
        total_distance += distance
        total_length += length
    return total_distance, total_length