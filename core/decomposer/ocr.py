"""Words on an image, by the text recognition built into macOS (the Vision framework): nothing to download, and
it reads small print well."""
from __future__ import annotations

import io


def words(image, correct: bool = False) -> list[tuple[str, tuple[float, float, float, float]]]:
    """(word, its box in the image's pixels) for every word found. ``correct``: let the recogniser bend what it
    reads toward dictionary words -- wrong for chord symbols."""
    import Vision
    from Foundation import NSData
    buf = io.BytesIO()
    image.save(buf, "PNG")
    data = NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(correct)
    Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None).performRequests_error_([request], None)
    W, H = image.size
    out = []
    for line in request.results() or []:
        best = line.topCandidates_(1)[0]
        text, at = best.string(), 0
        for word in text.split():
            at = text.index(word, at)
            found, _ = best.boundingBoxForRange_error_((at, len(word)), None)
            at += len(word)
            b = (found or line).boundingBox()
            out.append((word, (b.origin.x * W, (1 - b.origin.y - b.size.height) * H,
                               (b.origin.x + b.size.width) * W, (1 - b.origin.y) * H)))
    return out
