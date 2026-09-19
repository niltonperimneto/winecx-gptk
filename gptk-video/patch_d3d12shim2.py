import sys

def patch_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    missing_types = """
#ifndef __ID3D12VideoProcessCommandList_FWD_DEFINED__
#define __ID3D12VideoProcessCommandList_FWD_DEFINED__
DEFINE_GUID(IID_ID3D12VideoProcessCommandList, 0xAEB2543A, 0x167F, 0x4682, 0xAC, 0xC8, 0xD1, 0x59, 0xED, 0x4A, 0x62, 0x09);
#endif

#ifndef __ID3D12VideoProcessor_FWD_DEFINED__
#define __ID3D12VideoProcessor_FWD_DEFINED__
DEFINE_GUID(IID_ID3D12VideoProcessor, 0x304FDB32, 0xBEDE, 0x410A, 0x85, 0x45, 0x94, 0x3A, 0xC6, 0xA4, 0x61, 0x38);
#endif

#ifndef D3D12_VIDEO_PROCESS_OUTPUT_STREAM_ARGUMENTS_DEFINED
#define D3D12_VIDEO_PROCESS_OUTPUT_STREAM_ARGUMENTS_DEFINED

typedef struct D3D12_VIDEO_PROCESS_OUTPUT_STREAM {
    ID3D12Resource *pTexture2D;
    UINT Subresource;
} D3D12_VIDEO_PROCESS_OUTPUT_STREAM;

typedef struct D3D12_VIDEO_PROCESS_OUTPUT_STREAM_ARGUMENTS {
    D3D12_VIDEO_PROCESS_OUTPUT_STREAM OutputStream[2];
    D3D12_RECT TargetRectangle;
} D3D12_VIDEO_PROCESS_OUTPUT_STREAM_ARGUMENTS;

typedef enum D3D12_VIDEO_PROCESS_ORIENTATION {
    D3D12_VIDEO_PROCESS_ORIENTATION_DEFAULT = 0,
    D3D12_VIDEO_PROCESS_ORIENTATION_FLIP_HORIZONTAL = 1,
    D3D12_VIDEO_PROCESS_ORIENTATION_CLOCKWISE_90 = 2,
    D3D12_VIDEO_PROCESS_ORIENTATION_CLOCKWISE_90_FLIP_HORIZONTAL = 3,
    D3D12_VIDEO_PROCESS_ORIENTATION_CLOCKWISE_180 = 4,
    D3D12_VIDEO_PROCESS_ORIENTATION_FLIP_VERTICAL = 5,
    D3D12_VIDEO_PROCESS_ORIENTATION_CLOCKWISE_270 = 6,
    D3D12_VIDEO_PROCESS_ORIENTATION_CLOCKWISE_270_FLIP_HORIZONTAL = 7
} D3D12_VIDEO_PROCESS_ORIENTATION;

typedef enum D3D12_VIDEO_PROCESS_INPUT_STREAM_FLAGS {
    D3D12_VIDEO_PROCESS_INPUT_STREAM_FLAG_NONE = 0x0,
    D3D12_VIDEO_PROCESS_INPUT_STREAM_FLAG_FRAME_DISCONTINUITY = 0x1,
    D3D12_VIDEO_PROCESS_INPUT_STREAM_FLAG_FRAME_REPEAT = 0x2
} D3D12_VIDEO_PROCESS_INPUT_STREAM_FLAGS;

typedef struct D3D12_VIDEO_PROCESS_INPUT_STREAM_RATE {
    UINT OutputIndex;
    UINT InputFrameOrField;
} D3D12_VIDEO_PROCESS_INPUT_STREAM_RATE;

typedef struct D3D12_VIDEO_PROCESS_TRANSFORM {
    D3D12_RECT SourceRectangle;
    D3D12_RECT DestinationRectangle;
    D3D12_VIDEO_PROCESS_ORIENTATION Orientation;
} D3D12_VIDEO_PROCESS_TRANSFORM;

typedef struct D3D12_VIDEO_PROCESS_ALPHA_BLENDING {
    BOOL Enable;
    FLOAT Alpha;
} D3D12_VIDEO_PROCESS_ALPHA_BLENDING;

typedef struct D3D12_VIDEO_PROCESS_INPUT_STREAM {
    ID3D12Resource *pTexture2D;
    UINT Subresource;
    void *pReferenceInfo;
} D3D12_VIDEO_PROCESS_INPUT_STREAM;

typedef struct D3D12_VIDEO_PROCESS_INPUT_STREAM_ARGUMENTS {
    D3D12_VIDEO_PROCESS_INPUT_STREAM InputStream[2];
    D3D12_VIDEO_PROCESS_TRANSFORM Transform;
    D3D12_VIDEO_PROCESS_INPUT_STREAM_FLAGS Flags;
    D3D12_VIDEO_PROCESS_INPUT_STREAM_RATE RateInfo;
    INT FilterLevels[32];
    D3D12_VIDEO_PROCESS_ALPHA_BLENDING AlphaBlending;
} D3D12_VIDEO_PROCESS_INPUT_STREAM_ARGUMENTS;

#endif
"""

    if "D3D12_VIDEO_PROCESS_OUTPUT_STREAM_ARGUMENTS_DEFINED" not in content:
        content = content.replace('#include "yuvblit.h"', '#include "yuvblit.h"\n\n' + missing_types)
    else:
        # replace the previous injection block if it exists
        start_idx = content.find('#ifndef __ID3D12VideoProcessCommandList_FWD_DEFINED__')
        end_idx = content.find('#endif\n', start_idx + 1000)
        if start_idx != -1 and end_idx != -1:
            content = content[:start_idx] + missing_types + content[end_idx+7:]

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

patch_file("d3d12shim.c")
