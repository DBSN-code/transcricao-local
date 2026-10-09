#!/bin/sh
# Build a standalone audio converter from unmodified FFmpeg 9.0.2 sources.
# The source archive and this recipe accompany the distributed app.
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
TASK_SOURCE="$TASK_ROOT/build/vendor/ffmpeg-9.0.2"
cd "$TASK_SOURCE"
./configure \
    --cc=/usr/bin/clang --arch=arm64 --target-os=darwin \
    --extra-cflags=-mmacosx-version-min=27.0 --extra-ldflags=-mmacosx-version-min=27.0 \
    --disable-autodetect --disable-network --disable-doc --disable-debug \
    --disable-everything --disable-avdevice --disable-swscale \
    --disable-ffplay --disable-ffprobe --disable-asm \
    --enable-ffmpeg --enable-protocol=file,pipe \
    --enable-demuxer=ogg,matroska,mov,mp3,flac,wav,aiff \
    --enable-decoder=opus,vorbis,aac,alac,flac,mp3,mp3float,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s24be,pcm_s32le,pcm_s32be,pcm_f32le,pcm_f32be,pcm_f64le,pcm_f64be,pcm_u8,pcm_alaw,pcm_mulaw \
    --enable-parser=opus,vorbis,aac,flac,mpegaudio \
    --enable-encoder=pcm_s16le --enable-muxer=wav \
    --enable-filter=aresample,aformat,anull,atrim,asetpts
make -j4 ffmpeg
test -x ffmpeg
./ffmpeg -L
