"""부드러운 배경음악을 직접 합성한다 (저작권 없음). 곡 스타일을 여러 개 두고 영상마다 돌아가며 쓴다.
python bgm.py 출력.wav 길이초 번호"""
import sys, wave
import numpy as np

SR = 44100
# (이름, BPM, 으뜸음 MIDI, 진행(도수), 악기, 패턴)
STYLES = [
    ("따뜻한 피아노", 76, 60, [0, 4, 5, 3], "piano", "arp"),
    ("포근한 로즈", 70, 62, [5, 3, 0, 4], "epiano", "block"),
    ("오르골", 84, 67, [0, 5, 3, 4], "musicbox", "arp"),
    ("잔잔한 기타", 80, 57, [0, 3, 5, 4], "pluck", "arp"),
    ("새벽 패드 피아노", 66, 65, [3, 4, 2, 5], "piano", "slow"),
    ("카페 로즈", 88, 64, [0, 5, 1, 4], "epiano", "arp"),
    ("맑은 벨", 72, 69, [3, 0, 4, 5], "musicbox", "slow"),
    ("어쿠스틱 아침", 92, 62, [0, 4, 3, 4], "pluck", "block"),
]
SCALE = [0, 2, 4, 5, 7, 9, 11]


def hz(m): return 440 * 2 ** ((m - 69) / 12)


def note(inst, f, length, vol):
    t = np.arange(int(length * SR)) / SR
    if inst == "piano":
        s = sum(a * np.sin(2 * np.pi * f * h * t) * np.exp(-t * (2.2 + h)) for h, a in [(1, 1), (2, .45), (3, .2), (4, .1)])
        env = np.minimum(1, t / .005)
    elif inst == "epiano":
        s = (np.sin(2 * np.pi * f * t + .8 * np.sin(2 * np.pi * f * t) * np.exp(-t * 3)) * (1 + .15 * np.sin(2 * np.pi * 4.5 * t))) * np.exp(-t * 1.6)
        env = np.minimum(1, t / .01)
    elif inst == "musicbox":
        s = (np.sin(2 * np.pi * f * t) + .3 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 6)) * np.exp(-t * 2.5)
        env = np.minimum(1, t / .002)
    else:  # pluck: 카플러스-스트롱
        n = len(t); p = max(2, int(SR / f)); buf = np.random.default_rng(int(f)).uniform(-1, 1, p); s = np.zeros(n)
        for i in range(0, n, p):
            seg = buf[: min(p, n - i)]; s[i:i + len(seg)] = seg; buf = .5 * (buf + np.roll(buf, -1)) * .996
        env = np.ones(n)
    return vol * s * env


def pad(f, length, vol):
    t = np.arange(int(length * SR)) / SR
    s = sum(np.sin(2 * np.pi * f * d * t) for d in (1, 1.003, .997, 2.001)) / 4
    env = np.minimum(1, t / 1.2) * np.minimum(1, (length - t) / 1.0)
    return vol * s * np.clip(env, 0, 1)


def make(path, dur, idx):
    name, bpm, root, prog, inst, pat = STYLES[idx % len(STYLES)]
    N = int(SR * (dur + 2)); out = np.zeros(N); beat = 60 / bpm

    def add(sig, st):
        i = int(st * SR)
        if i < N: k = min(len(sig), N - i); out[i:i + k] += sig[:k]
    t, bar = 0.0, 0
    while t < dur + 1:
        d = prog[bar % 4]
        ch = [root + SCALE[(d + k) % 7] + 12 * ((d + k) // 7) for k in (0, 2, 4)]
        for m in ch: add(pad(hz(m - 12), beat * 4.3, .045), t)
        add(note("piano", hz(root - 24 + SCALE[d]), beat * 3.5, .10), t)  # 낮은 음
        if pat == "arp":
            seq = [0, 1, 2, 1, 2, 1, 0, 2] if bar % 2 == 0 else [0, 2, 1, 2, 0, 1, 2, 1]
            for k, j in enumerate(seq): add(note(inst, hz(ch[j] + 12), beat * 1.6, .07 if k % 2 == 0 else .05), t + k * beat / 2)
        elif pat == "block":
            for k in (0, 1.5, 2, 3): add(sum(note(inst, hz(m + 12), beat * 1.8, .035) for m in ch), t + k * beat)
        else:  # slow: 마디당 멜로디 두세 음
            for k, j in [(0, 2), (2, 1), (3, 0)]: add(note(inst, hz(ch[j] + 12), beat * 2.5, .07), t + k * beat)
        t += beat * 4; bar += 1
    # 부드럽게: 저역 통과 + 잔향(지수 감쇠 잡음과 컨볼루션)
    out = np.convolve(out, np.ones(12) / 12, mode="same")
    ir = np.random.default_rng(7).standard_normal(int(SR * 1.6)) * np.exp(-np.arange(int(SR * 1.6)) / SR * 3.2)
    L = len(out) + len(ir); F = 1 << (L - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(out, F) * np.fft.rfft(ir, F), F)[:len(out)]
    out = out + .18 * wet / (np.max(np.abs(wet)) + 1e-9) * np.max(np.abs(out))
    out = out[: int(SR * dur)]
    fi, fo = int(SR * 1.0), int(SR * 1.5)
    out[:fi] *= np.linspace(0, 1, fi); out[-fo:] *= np.linspace(1, 0, fo)
    out = out / (np.max(np.abs(out)) + 1e-9) * .8
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(np.repeat(pcm[:, None], 2, axis=1).tobytes())
    return name


if __name__ == "__main__":
    print(make(sys.argv[1], float(sys.argv[2]), int(sys.argv[3])))
