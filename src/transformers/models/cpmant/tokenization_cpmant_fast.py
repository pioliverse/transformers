# coding=utf-8
# Copyright 2022 The OpenBMB Team and The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tokenization classes for CPMAnt."""
import collections
import os
from importlib.util import find_spec
from typing import Optional, Tuple

from transformers import is_torch_available


if is_torch_available():
    import torch

if find_spec("jieba") is not None:
    import jieba
else:
    print(
        "You need to install jieba to use CPMAntTokenizer or CPMAntTokenizerFast. "
        "See https://pypi.org/project/jieba/ for installation."
    )
from ...tokenization_utils_fast import PreTrainedTokenizer
from ...utils import logging


logger = logging.get_logger(__name__)

VOCAB_FILES_NAMES = {"vocab_file": "vocab.txt", "tokenizer_file": "tokenizer.json"}

PRETRAINED_VOCAB_FILES_MAP = {
    "vocab_file": {
        "openbmb/cpm-ant-10b": "https://huggingface.co/cpm-ant-10b/resolve/main/vocab.txt",
    },
    "tokenizer_file": {
        "openbmb/cpm-ant-10b": "https://huggingface.co/cpm-ant-10b/resolve/main/tokenizer.json",
    },
}

PRETRAINED_POSITIONAL_EMBEDDINGS_SIZES = {
    "openbmb/cpm-ant-10b": 1024,
}


def pad(orig_items, key, padding_value=0, padding_side="left"):
    items = []
    if isinstance(orig_items[0][key], list):
        if not isinstance(orig_items[0][key][0], torch.Tensor):
            raise TypeError("The type of orig_items[0][key][0] should be tensor!")
        for it in orig_items:
            for tr in it[key]:
                items.append({key: tr})
    else:
        if not isinstance(orig_items[0][key][0], torch.Tensor):
            raise TypeError("The type of orig_items[0][key][0] should be tensor!")
        items = orig_items

    batch_size = len(items)
    shape = items[0][key].shape
    dim = len(shape)
    assert dim <= 3
    max_length = max(item[key].shape[-1] for item in items)
    min_length = min(item[key].shape[-1] for item in items)
    dtype = items[0][key].dtype

    if dim == 1:
        return torch.cat([item[key] for item in items], dim=0)
    elif dim == 2:
        if max_length == min_length:
            return torch.cat([item[key] for item in items], dim=0)
        tensor = torch.zeros((batch_size, max_length), dtype=dtype) + padding_value
    else:
        tensor = torch.zeros((batch_size, max_length, shape[-1]), dtype=dtype) + padding_value

    for i, item in enumerate(items):
        if dim == 2:
            if padding_side == "left":
                tensor[i, -len(item[key][0]) :] = item[key][0].clone()
            else:
                tensor[i, : len(item[key][0])] = item[key][0].clone()
        elif dim == 3:
            if padding_side == "left":
                tensor[i, -len(item[key][0]) :, :] = item[key][0].clone()
            else:
                tensor[i, : len(item[key][0]), :] = item[key][0].clone()

    return tensor


def load_vocab(vocab_file):
    """Loads a vocabulary file into a dictionary."""
    vocab = collections.OrderedDict()
    with open(vocab_file, "r", encoding="utf-8") as reader:
        tokens = reader.readlines()
    for index, token in enumerate(tokens):
        token = token.rstrip("\n")
        vocab[token] = index
    return vocab


class WordpieceTokenizer(object):
    def __init__(self, vocab, unk_token="<unk>", max_input_chars_per_word=200):
        self.vocab = vocab
        self.unk_token = unk_token
        self.max_input_chars_per_word = max_input_chars_per_word

    def tokenize(self, token):
        chars = list(token)
        if len(chars) > self.max_input_chars_per_word:
            return [self.unk_token]

        start = 0
        sub_tokens = []
        while start < len(chars):
            end = len(chars)
            cur_substr = None
            while start < end:
                substr = "".join(chars[start:end])
                if substr in self.vocab:
                    cur_substr = substr
                    break
                end -= 1
            if cur_substr is None:
                sub_tokens.append(self.unk_token)
                start += 1
            else:
                sub_tokens.append(cur_substr)
                start = end

        return sub_tokens


class CPMAntTokenizerFast(PreTrainedTokenizer):
    """
    Construct a "fast" CPMAnt tokenizer (backed by HuggingFace's *tokenizers* library).

    Args:
        vocab_file (`str`):
            Path to the vocabulary file.
    """

    vocab_files_names = VOCAB_FILES_NAMES
    pretrained_vocab_files_map = PRETRAINED_VOCAB_FILES_MAP
    max_model_input_sizes = PRETRAINED_POSITIONAL_EMBEDDINGS_SIZES
    model_input_names = ["input_ids", "attention_mask"]

    def __init__(
        self,
        vocab_file,
        tokenizer_file=None,
        bod_token="<d>",
        eod_token="</d>",
        bos_token="<s>",
        eos_token="</s>",
        pad_token="<pad>",
        unk_token="<unk>",
        line_token="</n>",
        space_token="</_>",
        **kwargs
    ):
        super().__init__(
            bod_token=bod_token,
            eod_token=eod_token,
            bos_token=bos_token,
            eos_token=eos_token,
            pad_token=pad_token,
            unk_token=unk_token,
            line_token=line_token,
            space_token=space_token,
            tokenizer_file=tokenizer_file,
            **kwargs,
        )
        self.bod_token = bod_token
        self.eod_token = eod_token
        self.encoder = load_vocab(vocab_file)
        self.encoder[" "] = self.encoder[space_token]
        self.encoder["\n"] = self.encoder[line_token]

        del self.encoder[space_token]
        del self.encoder[line_token]

        self.decoder = {v: k for k, v in self.encoder.items()}

        self.wordpiece_tokenizer = WordpieceTokenizer(vocab=self.encoder, unk_token=self.unk_token)

    @property
    def vocab_size(self):
        return len(self.encoder)

    @property
    def bod_id(self):
        return self.encoder[self.bod_token]

    @property
    def eod_id(self):
        return self.encoder[self.eod_token]

    @property
    def eos_id(self):
        return self.encoder[self.eos_token]

    @property
    def bos_id(self):
        return self.encoder[self.bos_token]

    @property
    def pad_id(self):
        return self.encoder[self.pad_token]

    @property
    def unk_id(self):
        return self.encoder[self.unk_token]

    @property
    def newline_id(self):
        return self.encoder["\n"]

    def __len__(self):
        return len(self.encoder)

    def tokenize(self, text):
        """Tokenize a string."""
        output_tokens = []
        for x in jieba.cut(text, cut_all=False):
            output_tokens.extend(self.wordpiece_tokenizer.tokenize(x))
        return output_tokens

    def encode(self, text):
        """Encode a string into ids."""
        return [self.encoder[x] for x in self.tokenize(text)]

    def decode(self, tokens, **kwargs):
        """Decode ids into a string."""
        if isinstance(tokens, torch.Tensor):
            tokens = tokens.detach().tolist()
        tokens = [i for i in tokens if i >= 0]
        text = "".join([self.decoder[x] for x in tokens])
        return text

    def check(self, token):
        return token in self.encoder

    def convert_tokens_to_ids(self, tokens):
        return [self.encoder.get(x, self.encoder[self.unk_token]) for x in tokens]

    def convert_ids_to_tokens(self, ids):
        return [self.decoder[x] if x >= 0 else self.unk_token for x in ids]

    def save_vocabulary(self, save_directory: str, filename_prefix: Optional[str] = None) -> Tuple[str]:
        if os.path.isdir(save_directory):
            vocab_file = os.path.join(
                save_directory, (filename_prefix + "-" if filename_prefix else "") + VOCAB_FILES_NAMES["vocab_file"]
            )
        else:
            vocab_file = (filename_prefix + "-" if filename_prefix else "") + save_directory
        index = 0
        with open(vocab_file, "w", encoding="utf-8") as writer:
            for token, token_index in self.encoder.items():
                if index != token_index:
                    logging.warning(
                        f"Saving vocabulary to {vocab_file}: vocabulary indices are not consecutive."
                        " Please check that the vocabulary is not corrupted!"
                    )
                    index = token_index
                writer.write(token + "\n")
                index += 1
        return (vocab_file,)

    def _convert_to_tensors(self, input_text, prompt_length=32, task_id=2):
        model_inputs = {}
        input_ids = [self.bos_id] + self.encode(input_text)
        input_ids = [j for j in input_ids if j != self.unk_id]

        model_inputs["input"] = [x + prompt_length * task_id for x in range(prompt_length)] + input_ids
        model_inputs["length"] = len(model_inputs["input"])
        model_inputs["position"] = list(range(len(model_inputs["input"])))
        model_inputs["span"] = [0] * len(model_inputs["input"])
        model_inputs["context"] = [True] * len(model_inputs["input"])
        model_inputs["segment"] = [0] * prompt_length + [2] * len(input_ids)

        for key in model_inputs:
            model_inputs[key] = torch.tensor(model_inputs[key]).int().unsqueeze(0)

        return model_inputs

    def get_model_input(self, text_list):
        input_tensors = list(map(self._convert_to_tensors, text_list))
        keys = set(input_tensors[0].keys())
        padded = {}
        for key in keys:
            padded[key] = pad(input_tensors, key, padding_side="left")
        return padded
