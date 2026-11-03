"""Inspect framing, clip encoding and chunking entirely offline."""
from pixeldeck.export import specimen
from pixeldeck.protocol import Decoder, READY, jpeg_clip, upload, brightness_packet
blob=jpeg_clip([specimen('buddy').render(0),specimen('buddy').render(1)],period_ms=250)
job=upload(blob)
print('CLIP BYTES',len(blob),'CHUNKS',len(job.chunks))
print('ANNOUNCE',job.announce.hex(' '))
print('READY DECODED',Decoder().feed(READY)==[READY])
print('BRIGHTNESS DRY RUN',brightness_packet(50).hex(' '))
