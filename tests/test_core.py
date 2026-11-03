import io
import json
import queue
import threading
import unittest
from PIL import Image
from pixeldeck.config import DeviceConfig
from pixeldeck.driver import MiniToo
from pixeldeck.engine import FramePump, Latest
from pixeldeck.inputs import decode_media, read_notices
from pixeldeck.protocol import READY, DONE, Decoder, packet, valid, jpeg_clip, upload, brightness_packet, fit_image
from pixeldeck.demos import CATALOG, create, register, Demo
from pixeldeck.deck import Deck

class FakeSocket:
    def __init__(self, ready=True, done=True, retransmit=False):
        self.incoming=queue.Queue(); self.sent=[]; self.ready=ready; self.done=done
        self.retransmit=retransmit; self.resent=False; self.closed=False; self.count=0; self.expected=0
    def settimeout(self,value): pass
    def connect(self,address): self.address=address
    def sendall(self,data):
        self.sent.append(data)
        if data[3]==0x32:
            self.incoming.put(packet(4,bytes([0x32,0x55,data[4]]))); return
        if data[4]==0:
            self.expected=(int.from_bytes(data[5:9],'little')+255)//256
            self.count=0
            if self.ready:
                self.incoming.put(READY[:4]); self.incoming.put(READY[4:])
        else:
            self.count+=1
            if self.count>=self.expected:
                if self.retransmit and not self.resent:
                    self.incoming.put(packet(4,b'\x8b\x55\x01\x00\x00')); self.resent=True
                elif self.done: self.incoming.put(DONE)
    def recv(self,n): return self.incoming.get()
    def shutdown(self,how): self.close()
    def close(self):
        if not self.closed: self.closed=True; self.incoming.put(b'')

class ProtocolTests(unittest.TestCase):
    def test_golden_ready_and_announce(self):
        self.assertEqual(packet(4,b'\x8b\x55\x00\x01'),READY)
        self.assertEqual(packet(0x8b,b'\x00\xa1\x2e\x00\x00').hex(),'0108008b00a12e0000620102')
    def test_fragmentation_and_multiple_packets(self):
        decoder=Decoder()
        self.assertEqual(decoder.feed(READY[:2]),[])
        self.assertEqual(decoder.feed(READY[2:]+DONE),[READY,DONE])
        self.assertEqual(len(decoder.buffer),0)
    def test_checksum_and_oversized_stream_fail(self):
        corrupt=bytearray(READY); corrupt[-2]^=1
        with self.assertRaises(ValueError): Decoder().feed(corrupt)
        with self.assertRaises(ValueError): Decoder().feed(bytes(65537))
    def test_jpeg_and_chunk_roundtrip(self):
        blob=jpeg_clip([Image.new('RGB',(160,128),'red')],250)
        self.assertEqual(blob[:6],bytes.fromhex('23 01 00 fa 08 0a'))
        job=upload(blob)
        self.assertEqual(b''.join(raw[11:-3] for raw in job.chunks),blob)
        self.assertTrue(all(valid(raw) for raw in (job.announce,*job.chunks)))
        with Image.open(io.BytesIO(blob[11:])) as image: self.assertEqual(image.size,(160,128))
    def test_clip_limits_and_brightness_validation(self):
        with self.assertRaises(ValueError): jpeg_clip([])
        with self.assertRaises(ValueError): jpeg_clip([Image.new('RGB',(10,10))])
        with self.assertRaises(ValueError): upload(bytes(16001))
        for value in (-1,101,True,1.2):
            with self.assertRaises(ValueError): brightness_packet(value)
    def test_transparent_image_is_composited(self):
        image=fit_image(Image.new('RGBA',(10,10),(255,0,0,0)))
        self.assertEqual(image.size,(160,128)); self.assertEqual(image.getbbox(),None)

class DriverTests(unittest.TestCase):
    def device(self,**kwargs):
        fake=FakeSocket(**kwargs)
        device=MiniToo(DeviceConfig(address='AA:BB:CC:DD:EE:FF',chunk_delay_ms=0,timeout=.06),socket_factory=lambda:fake)
        self.addCleanup(device.close); return device,fake
    def test_ready_data_ack_and_resend(self):
        device,fake=self.device(retransmit=True)
        report=device.show(Image.new('RGB',(160,128)))
        self.assertEqual(report['retransmissions'],1)
        self.assertEqual(len(fake.sent),report['chunks']+2)
    def test_no_ready_no_image_bytes(self):
        device,fake=self.device(ready=False)
        with self.assertRaises(TimeoutError): device.show(Image.new('RGB',(160,128)))
        self.assertEqual(len(fake.sent),1)
    def test_missing_done_fails(self):
        device,fake=self.device(done=False)
        with self.assertRaises(TimeoutError): device.show(Image.new('RGB',(160,128)))
    def test_brightness_ack(self):
        device,fake=self.device()
        self.assertEqual(device.brightness(50),50)
        self.assertEqual(fake.sent[0][3],0x32)
    def test_idle_heartbeat_memory_and_disconnect(self):
        fake=FakeSocket(); lost=threading.Event()
        device=MiniToo(DeviceConfig(address='AA:BB:CC:DD:EE:FF'),socket_factory=lambda:fake,on_disconnect=lambda _:lost.set())
        self.addCleanup(device.close)
        for i in range(1000): fake.incoming.put(packet(4,b'\xf7\x55\x00'))
        fake.incoming.put(b'')
        self.assertTrue(lost.wait(2)); self.assertEqual(len(device.trace),32)
        self.assertEqual(len(device._messages),0); self.assertFalse(device.healthy)

class EngineTests(unittest.TestCase):
    def test_idle_disconnect_resends_last_state_without_new_input(self):
        first_ack=threading.Event(); recovered=threading.Event(); sinks=[]; reports=[]
        class Sink:
            healthy=True
            def show(self,image): return {'transfer_ms':1}
            def close(self): self.healthy=False
        def factory():
            value=Sink(); sinks.append(value); return value
        def status(event):
            if event['type']=='frame.ack':
                reports.append(event)
                (first_ack if len(reports)==1 else recovered).set()
        pump=FramePump(factory,status); self.addCleanup(pump.close)
        pump.submit(Image.new('RGB',(160,128)))
        self.assertTrue(first_ack.wait(1)); sinks[0].healthy=False
        pump.reconnect(ConnectionError('simulated idle disconnect'))
        self.assertTrue(recovered.wait(1)); self.assertEqual(len(sinks),2)
        self.assertEqual([r['sequence'] for r in reports],[1,1])
    def test_pending_frames_are_constant_memory(self):
        latest=Latest()
        for i in range(10000): latest.put(i)
        self.assertEqual(latest.get(),9999); self.assertEqual(latest.replaced,9999)
        latest.close(); self.assertIsNone(latest.get())
    def test_input_submission_does_not_wait_for_upload(self):
        entered=threading.Event(); release=threading.Event(); last_ack=threading.Event(); seen=[]
        class Sink:
            def show(self,image):
                seen.append(image.getpixel((0,0))); entered.set()
                release.wait(2)
                return {'transfer_ms':1}
            def close(self): release.set()
        def status(event):
            if event['type']=='frame.ack' and event['sequence']==101: last_ack.set()
        pump=FramePump(Sink,status); self.addCleanup(pump.close)
        pump.submit(Image.new('RGB',(160,128),(0,0,0)))
        self.assertTrue(entered.wait(1))
        for i in range(1,101): pump.submit(Image.new('RGB',(160,128),(i,0,0)))
        self.assertEqual(len(seen),1)
        release.set(); self.assertTrue(last_ack.wait(2))
        self.assertEqual(seen,[(0,0,0),(100,0,0)])
        self.assertFalse(pump.submit(Image.new('RGB',(160,128),(100,0,0))))
    def test_finite_retry_budget(self):
        stopped=threading.Event(); calls=[]
        def fail(): calls.append(1); raise ConnectionError('simulated')
        pump=FramePump(fail,lambda e:stopped.set() if e['type']=='link.stopped' else None,retries=0)
        self.addCleanup(pump.close)
        pump.submit(Image.new('RGB',(160,128)))
        self.assertTrue(stopped.wait(1)); self.assertEqual(len(calls),1)
        self.assertFalse(pump.submit(Image.new('RGB',(160,128),'red')))

class DemoTests(unittest.TestCase):
    def test_custom_registration_and_collision(self):
        class Custom(Demo): key='unit-test-cartridge'
        register(Custom)
        try:
            self.assertIsInstance(create(Custom.key),Custom)
            with self.assertRaises(ValueError): register(Custom)
        finally: del CATALOG[Custom.key]
    def test_frozen_telemetry_requests_no_samples(self):
        demo=create('pulse'); demo.handle({'type':'telemetry','cpu':50,'memory':30},1)
        demo.handle({'type':'button'},2)
        demo.handle({'type':'telemetry','cpu':90,'memory':80},3)
        self.assertIsNone(demo.next_delay(3)); self.assertEqual(list(demo.samples),[50]); self.assertEqual(demo.ram,30)
    def test_all_demos_match_screen_and_encode(self):
        for name in CATALOG:
            with self.subTest(name=name):
                demo=create(name)
                for t in (0,1.25,100):
                    image=demo.render(t)
                    self.assertEqual(image.size,(160,128)); self.assertEqual(image.mode,'RGB')
                    self.assertLess(len(jpeg_clip([image])),16000)
    def test_no_timer_or_render_change_on_static_page(self):
        demo=create('buttons')
        self.assertIsNone(demo.next_delay(1))
        self.assertEqual(demo.render(1).tobytes(),demo.render(100).tobytes())
    def test_pause_cancels_animation_and_resume_preserves_phase(self):
        demo=create('rain'); demo.handle({'type':'button','button':'activate'},10)
        self.assertIsNone(demo.next_delay(100))
        self.assertEqual(demo.render(10).tobytes(),demo.render(100).tobytes())
        demo.handle({'type':'button','button':'activate'},110)
        self.assertEqual(demo.time(110),10)
    def test_focus_uses_elapsed_time_and_one_press(self):
        demo=create('focus'); event={'type':'button','button':'activate'}
        demo.handle(event,100); self.assertEqual(demo.left(125),35)
        demo.handle(event,125); self.assertEqual(demo.left(900),35); self.assertIsNone(demo.next_delay(900))
        demo.handle(event,900); demo.handle({'type':'tick'},940)
        self.assertEqual(demo.left(940),0); demo.handle(event,945); self.assertEqual(demo.left(945),60)
    def test_media_play_pause_both_advance_once(self):
        demo=create('buttons')
        for i,name in enumerate(['Pause','Play']*10):
            event=decode_media(json.dumps({'type':'button','value':name,'sequence':i}))
            demo.handle(event,i)
        self.assertEqual(demo.count,20)
    def test_notice_is_bounded_and_cannot_be_command(self):
        events=[]
        read_notices(io.StringIO('{"type":"notice","text":"HI"}\n{"type":"shell.run"}\n'),events.append)
        self.assertEqual([e['type'] for e in events],['notice','input.status'])
        demo=create('signal')
        for i in range(100): demo.handle({'type':'notice','text':'x'*1000},i)
        self.assertEqual(len(demo.messages),8); self.assertEqual(len(demo.messages[-1]),80)
    def test_navigation_and_hidden_notice(self):
        deck=Deck('buttons'); deck.handle({'type':'button','button':'previous'},1)
        self.assertEqual(deck.active.key,'focus')
        deck.handle({'type':'notice','text':'OK'},2)
        self.assertEqual(deck.demos['signal'].messages[-1],'OK')

if __name__=='__main__': unittest.main()
