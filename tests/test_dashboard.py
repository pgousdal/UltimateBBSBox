import json, pathlib, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
ROOT=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ubb_registry.loader import load_registry
from ubb_dashboard import DashboardApp, Handler
from ubb_observatory import Observatory

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); base=pathlib.Path(self.tmp.name); import shutil
        catalog=base/'catalog'; shutil.copytree(ROOT/'catalog',catalog); self.obs=Observatory(load_registry(catalog)); Handler.app=DashboardApp(self.obs)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler); self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start(); self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self): self.server.shutdown(); self.server.server_close(); self.tmp.cleanup()
    def get(self,path): return urllib.request.urlopen(self.url+path,timeout=2)
    def test_pages_and_api_are_read_only(self):
        for path in ('/','/services','/service/mystic-main','/sessions','/activity','/alerts','/readiness','/artifacts','/backups','/hosts'):
            self.assertEqual(self.get(path).status,200)
        for path in ('/api/v1/status','/api/v1/services','/api/v1/services/mystic-main','/api/v1/sessions','/api/v1/activity','/api/v1/alerts','/api/v1/readiness','/api/v1/artifacts','/api/v1/backups','/api/v1/hosts'):
            response=self.get(path); self.assertEqual(response.status,200); json.loads(response.read())
        request=urllib.request.Request(self.url+'/api/v1/status',method='POST')
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,405)
    def test_escaping_and_privacy(self):
        html=self.get('/').read().decode(); self.assertIn('ABBS',html); self.assertNotIn('password',html.lower()); self.assertNotIn('<script>',html.lower())
    def test_unknown_service_and_traversal_rejected(self):
        for path in ('/service/../../etc/passwd','/api/v1/services/../../etc/passwd','/api/v1/nope'):
            with self.assertRaises(urllib.error.HTTPError) as error: self.get(path)
            self.assertIn(error.exception.code,(404,400))

if __name__=='__main__': unittest.main()
