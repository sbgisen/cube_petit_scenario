# --- Internal motivational and existential state of CubePetit ---
# --- CubePetit の内的動機・存在状態 ---

# Degree of curiosity toward the environment (0.0 - 100.0)
# 環境に対する好奇心の度合い（0.0 - 100.0）
float32 curiosity

# Accumulated boredom level; increases over idle time (0.0 - 100.0)
# 退屈の蓄積度。アイドル状態で徐々に増加する（0.0 - 100.0）
float32 boredom

# Available internal energy level (0.0 - 100.0)
# 内部エネルギー残量（0.0 - 100.0）
float32 energy

# Tendency toward silence; higher values reduce spontaneous speech (0.0 - 100.0)
# 沈黙傾向。値が高いほど自発的な発話が抑制される（0.0 - 100.0）
float32 silence_bias

# Generation count of the physical body (incremented after restoration)
# 物理的身体の世代番号（復元後にインクリメントされる）
int32 body_generation

# Whether a human presence is currently detected
# 現在、人の存在が検出されているか
bool human_detected

# Whether another CubePetit (peer entity) is detected nearby
# 他の CubePetit（同種個体）が近くに検出されているか
bool petit_detected

bool sleep_mode
