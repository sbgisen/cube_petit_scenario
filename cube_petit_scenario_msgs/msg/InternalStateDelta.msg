# Additive delta applied to InternalState once per tick.
# InternalState に加算される影響量（1 tickごとに反映）

float32 d_curiosity
float32 d_boredom
float32 d_energy
float32 d_silence_bias

bool human_detected
bool petit_detected
bool sleep_request

# Priority / weight (0.0 - 1.0). 1.0 = fully trusted.
# 信頼度・重み (0.0 - 1.0)
float32 weight

# Optional source name (e.g., "mic_vad", "face_detector")
# 任意：ソース名
string source
