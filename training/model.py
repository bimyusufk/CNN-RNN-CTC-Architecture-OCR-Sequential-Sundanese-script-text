# -*- coding: utf-8 -*-
"""CRNN architecture exactly matching Tabel 3.1 / 3.2 of
Proposal_SekuensialAksaraSunda: 4-block conv backbone (asymmetric pooling --
height collapses to 1, width preserved as the time axis) -> 2-layer BiLSTM
(256 hidden, fixed regardless of width multiplier -- Tabel 3.2 only scales
the 4 conv layers) -> linear projection -> CTC.

Width-multiplier channel counts (Tabel 3.2), keyed by alpha:
    0.25 -> (8, 16, 32, 32)
    0.50 -> (16, 32, 64, 64)
    0.75 -> (24, 48, 96, 96)
    1.00 -> (32, 64, 128, 128)   (base)
    1.50 -> (48, 96, 192, 192)
"""
import torch
import torch.nn as nn

WIDTH_CHANNELS = {
    0.25: (8, 16, 32, 32),
    0.50: (16, 32, 64, 64),
    0.75: (24, 48, 96, 96),
    1.00: (32, 64, 128, 128),
    1.50: (48, 96, 192, 192),
}

INPUT_HEIGHT = 32
LSTM_HIDDEN = 256


class CRNN(nn.Module):
    def __init__(self, num_classes, width_mult=1.00):
        """num_classes: C+1 (real symbol classes + 1 CTC blank, index 0)."""
        super().__init__()
        if width_mult not in WIDTH_CHANNELS:
            raise ValueError(f"width_mult harus salah satu dari {list(WIDTH_CHANNELS)}")
        c1, c2, c3, c4 = WIDTH_CHANNELS[width_mult]
        self.width_mult = width_mult
        self.channels = (c1, c2, c3, c4)

        def conv_bn_relu(cin, cout):
            return nn.Sequential(
                nn.Conv2d(cin, cout, kernel_size=3, padding=1),
                nn.BatchNorm2d(cout),
                nn.ReLU(inplace=True),
            )

        self.conv1 = conv_bn_relu(1, c1)
        self.pool1 = nn.MaxPool2d(2, 2)            # 32xW   -> 16 x W/2
        self.conv2 = conv_bn_relu(c1, c2)
        self.pool2 = nn.MaxPool2d(2, 2)            # 16xW/2 -> 8  x W/4
        self.conv3 = conv_bn_relu(c2, c3)
        self.pool3 = nn.MaxPool2d((2, 1), (2, 1))  # 8xW/4  -> 4  x W/4
        self.conv4 = conv_bn_relu(c3, c4)
        self.pool4 = nn.MaxPool2d((2, 1), (2, 1))  # 4xW/4  -> 2  x W/4
        self.adaptive_pool = nn.AdaptiveAvgPool2d((1, None))  # 2xW/4 -> 1 x W/4

        self.lstm = nn.LSTM(c4, LSTM_HIDDEN, num_layers=2, bidirectional=True,
                             batch_first=True)
        self.fc = nn.Linear(LSTM_HIDDEN * 2, num_classes)

    def encode(self, x):
        """x: (B, 1, 32, W) -> (B, T=W/4, 2*LSTM_HIDDEN) -- the shared
        backbone+BiLSTM representation, BEFORE the CTC projection. This is
        what an auxiliary training-time decoder (see AuxDecoder below)
        reads via cross-attention, same "shared encoder feeds two heads"
        pattern as PP-OCRv6's CTC+NRTR (Zhang et al. 2026) and GTC (Hu et
        al. 2020) -- the CTC head stays the only one used at inference, so
        the deployed architecture is still exactly CRNN+CTC."""
        x = self.pool1(self.conv1(x))
        x = self.pool2(self.conv2(x))
        x = self.pool3(self.conv3(x))
        x = self.pool4(self.conv4(x))
        x = self.adaptive_pool(x)          # (B, C4, 1, W/4)
        x = x.squeeze(2)                   # (B, C4, W/4)
        x = x.permute(0, 2, 1)             # (B, T=W/4, C4)
        x, _ = self.lstm(x)                # (B, T, 2*hidden)
        return x

    def forward(self, x):
        """x: (B, 1, 32, W) -> (T, B, num_classes) log-probs, CTC convention
        (time-major). This is the ONLY path used at inference / deployment."""
        features = self.encode(x)
        x = self.fc(features)              # (B, T, num_classes)
        x = x.permute(1, 0, 2)             # (T, B, num_classes) for CTCLoss
        return torch.log_softmax(x, dim=2)

    def count_params(self):
        return sum(p.numel() for p in self.parameters())


# --- auxiliary training-only decoder (discarded at inference) -------------

AUX_PAD, AUX_BOS, AUX_EOS = 0, 1, 2
AUX_SPECIAL_TOKENS = 3  # ctc_idx (1..N) maps to aux_idx = ctc_idx + 2


def ctc_ids_to_aux_ids(ctc_ids):
    """CTC target ids (1..N, blank=0 never appears in targets) -> aux
    vocabulary ids (shifted by AUX_SPECIAL_TOKENS-1 to make room for
    PAD/BOS/EOS)."""
    return [i + (AUX_SPECIAL_TOKENS - 1) for i in ctc_ids]


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=200):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-torch.log(torch.tensor(10000.0)) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]


class AuxDecoder(nn.Module):
    """A small Transformer decoder trained ALONGSIDE the CRNN's CTC head,
    reading the same shared CNN+BiLSTM feature sequence via cross-attention
    and predicting the target sequence autoregressively (teacher forcing,
    cross-entropy with label smoothing) -- an implicit language-model
    regularizer for the shared representation. Same role as NRTR in
    PP-OCRv6 / the attention branch in GTC (Hu et al. 2020): present only
    during training, thrown away at inference, CTC remains the sole
    deployed decoding path."""

    def __init__(self, memory_dim, aux_vocab_size, d_model=256, nhead=4,
                 num_layers=2, dim_feedforward=512, dropout=0.1, max_len=750):
        # max_len=750: history-corpus sentences push max n_symbols in train
        # to 683 (vs <=200 when this default was set against NusaAksara
        # alone) -- margin above the observed max, not the max itself.
        super().__init__()
        self.d_model = d_model
        self.memory_proj = nn.Linear(memory_dim, d_model)
        self.tok_embed = nn.Embedding(aux_vocab_size, d_model, padding_idx=AUX_PAD)
        self.pos_enc = PositionalEncoding(d_model, max_len=max_len)
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
            dropout=dropout, batch_first=True)
        self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        self.out_proj = nn.Linear(d_model, aux_vocab_size)

    def forward(self, memory, tgt_input, tgt_key_padding_mask=None):
        """memory: (B, T, memory_dim) from CRNN.encode(). tgt_input: (B, L)
        token ids, teacher-forcing input (BOS + shifted target).
        Returns logits (B, L, aux_vocab_size)."""
        memory = self.memory_proj(memory)
        tgt = self.tok_embed(tgt_input) * (self.d_model ** 0.5)
        tgt = self.pos_enc(tgt)
        L = tgt.size(1)
        causal_mask = torch.triu(torch.ones(L, L, device=tgt.device, dtype=torch.bool), diagonal=1)
        out = self.decoder(tgt, memory, tgt_mask=causal_mask,
                            tgt_key_padding_mask=tgt_key_padding_mask)
        return self.out_proj(out)


class TrivialBaselineCNN(nn.Module):
    """The 'trivial segmentation' baseline: a plain isolated-syllable
    classifier (NOT sequential/CTC). At eval time, syllable crops are taken
    from KNOWN positions (synthesis metadata), each classified independently,
    predictions concatenated in order -- valid only because segmentation is
    free-by-construction in our synthetic data, not a real detector.
    Architecture: same 4-block conv backbone as CRNN's base width (1.00),
    reused per the proposal's own framing ("reuse the isolated-character
    classifier"), + global pool + FC to num_classes (no blank needed, this
    is plain classification, not CTC)."""

    def __init__(self, num_classes):
        super().__init__()
        c1, c2, c3, c4 = WIDTH_CHANNELS[1.00]

        def conv_bn_relu(cin, cout):
            return nn.Sequential(
                nn.Conv2d(cin, cout, kernel_size=3, padding=1),
                nn.BatchNorm2d(cout),
                nn.ReLU(inplace=True),
            )

        self.features = nn.Sequential(
            conv_bn_relu(1, c1), nn.MaxPool2d(2, 2),
            conv_bn_relu(c1, c2), nn.MaxPool2d(2, 2),
            conv_bn_relu(c2, c3), nn.MaxPool2d(2, 2),
            conv_bn_relu(c3, c4), nn.MaxPool2d(2, 2),
        )
        self.global_pool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(c4, num_classes)

    def forward(self, x):
        x = self.features(x)
        x = self.global_pool(x).flatten(1)
        return self.fc(x)
