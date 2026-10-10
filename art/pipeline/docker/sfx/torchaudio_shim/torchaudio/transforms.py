"""Sinc-interpolation Resample, a pure-torch port of torchaudio.functional.resample."""
import math
import torch
import torch.nn.functional as F


def _kernel(orig_freq, new_freq, lowpass_filter_width=6, rolloff=0.99, dtype=None, device=None):
    base_freq = min(orig_freq, new_freq) * rolloff
    width = math.ceil(lowpass_filter_width * orig_freq / base_freq)
    idx = torch.arange(-width, width + orig_freq, dtype=dtype or torch.float32, device=device)[None, None] / orig_freq
    t = torch.arange(0, -new_freq, -1, dtype=dtype or torch.float32, device=device)[:, None, None] / new_freq + idx
    t *= base_freq
    t = t.clamp_(-lowpass_filter_width, lowpass_filter_width)
    window = torch.cos(t * math.pi / lowpass_filter_width / 2) ** 2
    t *= math.pi
    scale = base_freq / orig_freq
    kernels = torch.where(t == 0, torch.tensor(1.0, dtype=t.dtype, device=t.device), t.sin() / t)
    kernels *= window * scale
    return kernels, width


class Resample(torch.nn.Module):
    def __init__(self, orig_freq=16000, new_freq=16000, lowpass_filter_width=6, rolloff=0.99, dtype=None):
        super().__init__()
        g = math.gcd(int(orig_freq), int(new_freq))
        self.orig_freq, self.new_freq = int(orig_freq) // g, int(new_freq) // g
        k, w = _kernel(self.orig_freq, self.new_freq, lowpass_filter_width, rolloff, dtype)
        self.register_buffer("kernel", k)
        self.width = w

    def forward(self, waveform):
        if self.orig_freq == self.new_freq:
            return waveform
        shape = waveform.shape
        x = waveform.reshape(-1, shape[-1])
        n = x.shape[-1]
        x = F.pad(x[:, None], (self.width, self.width + self.orig_freq))
        y = F.conv1d(x, self.kernel.to(x.dtype), stride=self.orig_freq)
        y = y.transpose(1, 2).reshape(x.shape[0], -1)
        target = int(math.ceil(self.new_freq * n / self.orig_freq))
        return y[..., :target].reshape(shape[:-1] + (target,))
