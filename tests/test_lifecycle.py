"""Hidden GUI, no Bluetooth/audio. Exercises the actual local stop IPC."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from pixeldeck.config import DeviceConfig

@unittest.skipUnless(os.name=='nt','Windows GUI integration')
class LifecycleTests(unittest.TestCase):
    def test_twenty_actions_then_stop_and_release(self):
        from pixeldeck.app import Application
        from pixeldeck.control import stop
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,{'PIXELDECK_HOME':directory}):
                app=Application(DeviceConfig(),demo='buttons',duration=10)
                app.root.withdraw(); result=[]; started=False
                def quit(): result.append(stop(Path(directory)))
                def inspect(_):
                    nonlocal started
                    count=app.deck.active.count
                    if count<20: app.button('activate')
                    elif not started:
                        started=True; threading.Thread(target=quit,daemon=True).start()
                app.root.bind('<<Events>>',inspect,add='+')
                app.root.after(50,lambda:app.button('activate'))
                app.run()
                self.assertEqual(app.deck.active.count,20)
                self.assertEqual(result,[True]); self.assertTrue(app.lock.file.closed)
                self.assertIsNone(app.pump); self.assertIsNone(app.media)
                self.assertFalse((Path(directory)/'control.json').exists())
