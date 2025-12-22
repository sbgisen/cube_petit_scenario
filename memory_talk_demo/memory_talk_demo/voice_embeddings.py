#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
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
#

import os
import time
from typing import Optional, Protocol

from audio_common_msgs.msg import AudioDataStamped
from audio_common_msgs.msg import AudioInfo
import numpy as np
import onnxruntime as ort
import rclpy
from rclpy.node import Node
from resemblyzer import preprocess_wav
from resemblyzer import VoiceEncoder
from speechbrain.lobes.models.ECAPA_TDNN import TDNNBlock
from speechbrain.pretrained import EncoderClassifier
from std_msgs.msg import Float32MultiArray
from std_msgs.msg import String
import torch
import torchaudio
from torchaudio.functional import highpass_biquad
from torchaudio.functional import lowpass_biquad


class _TDNNBlockLike(Protocol):
    """Minimal protocol for speechbrain TDNNBlock used in monkey patch."""
    conv: torch.nn.Module
    activation: torch.nn.Module
    norm: torch.nn.Module


def _patched_tdnn_forward(
    self: _TDNNBlockLike,
    x: torch.Tensor,
    lengths: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    """Patched forward function for TDNNBlock (ignores lengths)."""
    return self.norm(self.activation(self.conv(x)))


TDNNBlock.forward = _patched_tdnn_forward  # type: ignore[assignment]


class VoiceEmbeddingNode(Node):
    """
    ROS 2 node for speaker embedding extraction and benchmarking.

    Compares:
    - ONNX ECAPA-TDNN
    - SpeechBrain ECAPA-TDNN
    - Resemblyzer
    """

    def __init__(self) -> None:
        """Initialize node, models, and inference backends."""
        super().__init__('voice_embedding_node')

        self.declare_parameter('wav_path', '/tmp/audio_saver/detected_20251217_170941_718257.wav')
        self.wav_path = self.get_parameter('wav_path').get_parameter_value().string_value

        self.pub_embed = self.create_publisher(Float32MultiArray, 'voice_embedding', 10)
        self.pub_info = self.create_publisher(String, 'voice_embedding_info', 10)

        torch.set_default_tensor_type(torch.FloatTensor)

        self.get_logger().info('Loading ECAPA-TDNN model (CPU mode)...')
        self.classifier = EncoderClassifier.from_hparams(source='speechbrain/spkrec-ecapa-voxceleb',
                                                         run_opts={'device': 'cpu'})
        self.get_logger().info('Model loaded.')

        self.sess: ort.InferenceSession = self._prepare_onnx()

        # self.process_onnx()
        # self.process_audio()
        # self.process_resemblyzer()

        self.current_audio_info: Optional[AudioInfo] = None
        self.sub_audio_stamped = self.create_subscription(AudioDataStamped, 'realtime_audio_stamped',
                                                          self.handle_subscribe_audio_stamped, 10)
        self.sub_audio_info = self.create_subscription(AudioInfo, 'realtime_audio_info',
                                                       self.handle_subscribe_audio_info, 10)

        self.previous_emb = None

    def handle_subscribe_audio_info(self, msg: AudioInfo) -> None:
        """Store latest AudioInfo for subsequent AudioDataStamped."""
        self.current_audio_info = msg
        self.get_logger().info(f'Received AudioInfo: '
                               f'ch={msg.channels}, '
                               f'sr={msg.sample_rate}, '
                               f'fmt={msg.sample_format}, '
                               f'coding={msg.coding_format}')

    def handle_subscribe_audio_stamped(self, msg: AudioDataStamped) -> None:
        """
        Handle AudioDataStamped message and extract speaker embedding using ONNX ECAPA.

        Assumptions:
        - PCM16 mono or multi-channel audio
        - Embedding is extracted from the entire message payload
        """
        if self.current_audio_info is None:
            self.get_logger().warn('AudioDataStamped received but AudioInfo is not available yet')
            return

        info = self.current_audio_info
        if info.sample_format != 'S16LE':
            self.get_logger().error(f'Unsupported sample format: {info.sample_format}')
            return

        pcm = np.frombuffer(msg.audio.data, dtype=np.int16)
        if pcm.size == 0:
            self.get_logger().warn('Received empty audio buffer')
            return

        if info.channels > 1:
            pcm = pcm.reshape(-1, info.channels).mean(axis=1)

        waveform = pcm.astype(np.float32) / 32768.0
        waveform_t = torch.from_numpy(waveform).unsqueeze(0)

        sample_rate = info.sample_rate
        if sample_rate != 16000:
            waveform_t = torchaudio.transforms.Resample(sample_rate, 16000)(waveform_t)
            sample_rate = 16000

        t0 = time.perf_counter()

        pcm: np.ndarray = np.frombuffer(msg.audio.data, dtype=np.int16)
        if pcm.size == 0:
            self.get_logger().warn('Received empty audio buffer')
            return

        mel_transform = torchaudio.transforms.MelSpectrogram(
            sample_rate=sample_rate,
            n_fft=400,
            win_length=400,
            hop_length=160,
            n_mels=80,
            f_min=20,
            f_max=7600,
        )
        mel: torch.Tensor = torch.log(mel_transform(waveform_t) + 1e-6)
        t1: float = time.perf_counter()
        embedding: np.ndarray = self.sess.run(None, {'mel_features': mel.numpy().astype(np.float32)})[0].squeeze()
        embedding = embedding / np.linalg.norm(embedding)
        t2: float = time.perf_counter()
        embed_msg = Float32MultiArray(data=embedding.tolist())

        self.pub_embed.publish(embed_msg)
        self.get_logger().info(f'⏱ AudioStamped: mel={((t1 - t0) * 1000):.1f} ms, '
                               f'infer={((t2 - t1) * 1000):.1f} ms, '
                               f'total={((t2 - t0) * 1000):.1f} ms')

        self.get_logger().info(f'Embedding received from AudioStamped '
                               f'(dim={embedding.shape[0]})')

        if self.previous_emb is not None:
            prev: np.ndarray = self.previous_emb
            sim: float = float(np.dot(embedding, prev) / (np.linalg.norm(embedding) * np.linalg.norm(prev)))
            self.get_logger().info(f'Cosine similarity: {sim:.3f}')

        self.previous_emb = embedding

    def _prepare_onnx(self) -> ort.InferenceSession:
        """Export ECAPA-TDNN to ONNX and return ONNX Runtime session."""
        embedding_model: torch.nn.Module = (self.classifier.mods.embedding_model)

        class ECAPAWrapper(torch.nn.Module):
            """Wrapper to adapt ECAPA input format for ONNX."""

            def __init__(self, model: torch.nn.Module) -> None:
                super().__init__()
                self.model: torch.nn.Module = model

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                x = x.transpose(1, 2)
                return self.model(x)

        onnx_path: str = ('/home/gisen/ros/src/cube_petit_scenario/'
                          'memory_talk_demo/resource/ecapa_voxceleb.onnx')

        if not os.path.exists(onnx_path):
            self.get_logger().info('Exporting ECAPA-TDNN to ONNX...')
            dummy_input: torch.Tensor = torch.randn(1, 80, 101)
            torch.onnx.export(ECAPAWrapper(embedding_model),
                              dummy_input,
                              onnx_path,
                              input_names=['mel_features'],
                              output_names=['embedding'],
                              dynamic_axes={'mel_features': {
                                  2: 'num_frames'
                              }},
                              opset_version=13)
            self.get_logger().info('ONNX export complete.')

        return ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])

    def _log_time(self, label: str, start_t: float) -> None:
        """Log elapsed time in milliseconds."""
        elapsed_ms: float = (time.perf_counter() - start_t) * 1000.0
        self.get_logger().info(f'⏱ {label}: {elapsed_ms:.1f} ms')

    def process_onnx(self) -> np.ndarray:
        """Run ONNX-based ECAPA-TDNN inference and return embedding."""
        t0: float = time.perf_counter()

        waveform: torch.Tensor
        sr: int
        waveform, sr = torchaudio.load(self.wav_path)

        if sr != 16000:
            waveform = torchaudio.transforms.Resample(sr, 16000)(waveform)
            sr = 16000

        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        mel_transform = torchaudio.transforms.MelSpectrogram(
            sample_rate=sr,
            n_fft=400,
            win_length=400,
            hop_length=160,
            n_mels=80,
            f_min=20,
            f_max=7600,
        )

        mel: torch.Tensor = torch.log(mel_transform(waveform) + 1e-6)
        self._log_time('ONNX: mel extraction', t0)

        t1: float = time.perf_counter()
        outputs = self.sess.run(None, {'mel_features': mel.numpy().astype(np.float32)})
        embedding: np.ndarray = outputs[0].squeeze()

        self._log_time('ONNX: inference', t1)
        self._log_time('ONNX: total', t0)

        self.get_logger().info(f'Embedding shape: {embedding.shape}')
        return embedding

    def process_audio(self) -> np.ndarray:
        """Run SpeechBrain ECAPA-TDNN and return embedding."""
        if not os.path.exists(self.wav_path):
            raise FileNotFoundError(self.wav_path)

        t0: float = time.perf_counter()

        waveform: torch.Tensor
        sr: int
        waveform, sr = torchaudio.load(self.wav_path)

        waveform = lowpass_biquad(waveform, sr, 4000)
        waveform = highpass_biquad(waveform, sr, 100)
        waveform = (waveform - waveform.mean()) / (waveform.abs().max() + 1e-8)

        self._log_time('SpeechBrain: preprocess', t0)

        t1: float = time.perf_counter()
        embeddings: torch.Tensor = (self.classifier.encode_batch(waveform))

        self._log_time('SpeechBrain: encode_batch', t1)
        self._log_time('SpeechBrain: total', t0)

        embedding: np.ndarray = (embeddings.squeeze().cpu().numpy())

        msg = Float32MultiArray(data=embedding.tolist())
        self.pub_embed.publish(msg)

        info_msg: str = (f'Embedding dim={embeddings.shape[-1]}, '
                         f'mean={float(torch.mean(embeddings)):.4f}, '
                         f'std={float(torch.std(embeddings)):.4f}')
        self.pub_info.publish(String(data=info_msg))
        self.get_logger().info(info_msg)

        return embedding

    def process_resemblyzer(self) -> np.ndarray:
        """Run Resemblyzer and return embedding."""
        if not os.path.exists(self.wav_path):
            raise FileNotFoundError(self.wav_path)

        t0: float = time.perf_counter()
        encoder: VoiceEncoder = VoiceEncoder(device='cpu')
        wav: np.ndarray = preprocess_wav(self.wav_path)
        self._log_time('Resemblyzer: preprocess', t0)

        t1: float = time.perf_counter()
        embedding: np.ndarray = encoder.embed_utterance(wav)

        self._log_time('Resemblyzer: embed', t1)
        self._log_time('Resemblyzer: total', t0)

        return embedding


def main() -> None:
    """ROS 2 entry point."""
    rclpy.init()
    node: VoiceEmbeddingNode = VoiceEmbeddingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
