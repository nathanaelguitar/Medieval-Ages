"""Minimal torchaudio stand-in for the sa3-sfx image.

PyPI torchaudio wheels are built against stock torch and fail to dlopen against NVIDIA's
torch 2.10.0a0 (undefined symbol torch_get_mutable_data_ptr). stable-audio-3 only uses
torchaudio.transforms.Resample (and only when input audio has a different sample rate), plus
torchaudio.load/save in its CLI, so those are provided here in pure torch + soundfile.
"""
import soundfile as _sf
import torch as _torch
from . import transforms  # noqa: F401

__version__ = "0.0-shim"


def load(path):
    data, sr = _sf.read(path, dtype="float32", always_2d=True)
    return _torch.from_numpy(data.T.copy()), sr


def save(path, waveform, sample_rate):
    _sf.write(path, waveform.detach().cpu().numpy().T, sample_rate)
