import json
import os
from pathlib import Path
import unittest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webapp.settings')
import django
from django.test import Client

django.setup()
ROOT = Path(__file__).resolve().parents[1]


class APITests(unittest.TestCase):
    def setUp(self):

        self.client = Client(enforce_csrf_checks=True)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.token = response.cookies['csrftoken'].value

    def post(self, url, value):
        return self.client.post(url, json.dumps(value), content_type='application/json', HTTP_X_CSRFTOKEN=self.token)

    def test_examples_3_5_without_coordinates_and_finite_horizon(self):
        for name in ('example3_grid.json','example3_small.json','example4_weighted.json','example5_unreachable.json'):
            with self.subTest(name=name):
                data = json.loads((ROOT/'examples'/name).read_text())
                response = self.post('/api/graph/validate/',data)
                self.assertEqual(response.status_code,200,response.content)
                document = response.json()['document']
                self.assertTrue(all('coordinates' not in v for v in document['graph']['vertices']))
                for method, parameters in (('exact',{}),('relaxation',{}),('finite_horizon',{'T':2})):
                    response = self.post('/api/run/',{'document':document,'method':method,'parameters':parameters})
                    self.assertEqual(response.status_code,200,response.content)
                    run=response.json()
                    self.assertEqual(run['start_id'],document['graph']['start_id'])
                    self.assertTrue(all('coordinates' not in v for v in run['document']['graph']['vertices']))
                    if method == 'finite_horizon':
                        self.assertTrue(all(type(run['result'][key]) in (float,int) for key in ('P','Q','U')))
                        self.assertAlmostEqual(sum(run['result'][key] for key in ('P','Q','U')),1)
                    elif method == 'relaxation':
                        self.assertIn('max_abs_error',run['history'][0])

    def test_finite_horizon_expected_and_target_at_step_zero(self):
        data=json.loads((ROOT/'examples/example3_small.json').read_text())
        run=self.post('/api/run/',{'document':data,'method':'finite_horizon','parameters':{'T':2}}).json()
        self.assertEqual({k:run['result'][k] for k in ('P','Q','U')},{'P':.25,'Q':.5,'U':.25})
        run=self.post('/api/run/',{'document':data,'method':'finite_horizon','parameters':{'T':0},'start_id':'green'}).json()
        self.assertEqual({k:run['result'][k] for k in ('P','Q','U')},{'P':1,'Q':0,'U':0})

    def test_api_monte_carlo_repeatable_and_history(self):
        data=json.loads((ROOT/'examples/example4_weighted.json').read_text())
        request={'document':data,'method':'monte_carlo','parameters':{'samples':1000,'seed':7,'max_steps':1,'batch_size':100}}
        first=self.post('/api/run/',request)
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json(),self.post('/api/run/',request).json())
        self.assertEqual(len(first.json()['history']),10)

    def test_invalid_json_role_weights_start_parameters(self):
        for invalid in ([], {}, {'schema_version':True}, {'schema_version':1,'graph':[]},
                        {'schema_version':1,'graph':{'vertices':[1],'edges':[]}}):
            response=self.post('/api/graph/validate/',invalid)
            self.assertEqual(response.status_code,400,response.content)
            self.assertIn('error',response.json())
        base=json.loads((ROOT/'examples/example3_small.json').read_text())
        for value in (3,True,1.0,'blue'):
            data=json.loads(json.dumps(base));data['graph']['vertices'][0]['role']=value
            self.assertEqual(self.post('/api/graph/validate/',data).status_code,400)
        for weight in (-1,0,True):
            data=json.loads(json.dumps(base));data['graph']['edges'][0]['weight']=weight
            self.assertEqual(self.post('/api/graph/validate/',data).status_code,400)
        for changes in ({'start_id':'missing'},{'method':'absent'},{'parameters':{'T':-1}},{'parameters':[]}):
            request={'document':base,'method':'finite_horizon',**changes}
            self.assertEqual(self.post('/api/run/',request).status_code,400)
        response=self.client.post('/api/run/','{',content_type='application/json',HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.post('/api/run/','{}',content_type='application/json').status_code,403)

    def test_example_listing_and_no_unknown_file_read(self):
        listing=self.client.get('/api/examples/').json()['examples']
        self.assertIn('example5_unreachable.json',listing)
        for name in listing:
            response=self.client.get(f'/api/examples/{name}/')
            self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(self.client.get('/api/examples/settings.py/').status_code,400)
