"""Exercise the extracted wheel only; no ML backend, model or real-user claims."""
import json
import sys
from pathlib import Path

extracted, qa = map(lambda value: Path(value).resolve(), sys.argv[1:3])
sys.path.insert(0, str(extracted))
import kitguard
from fastapi.testclient import TestClient
from kitguard.app import create_app
from kitguard import detector_worker, inspection_jobs, manual_review, readiness, task_trial_api, task_trials

assert Path(kitguard.__file__).resolve().is_relative_to(extracted)
assert kitguard.__version__ == '0.6.0.dev2'
assert 'torch' not in sys.modules and 'mlx' not in sys.modules and 'mlx_vlm' not in sys.modules
for module in (detector_worker, inspection_jobs, manual_review, readiness, task_trial_api, task_trials):
    assert Path(module.__file__).resolve().is_relative_to(extracted), module.__file__

class Observer:
    def status(self):
        return {'available': False, 'loaded': False, 'label': 'ENGINEERING WHEEL FIXTURE',
                'error': 'No real model used by wheel verification'}
    def observe(self, *_args, **_kwargs):
        raise AssertionError('Wheel smoke must never run inference')

statuses = {}
with TestClient(create_app(data_dir=qa / 'testclient-engineering-data', analyzer=Observer())) as client:
    response = client.get('/api/health')
    assert response.status_code == 200 and response.json()['version'] == '0.6.0.dev2'
    statuses['/api/health'] = response.status_code
    for path in sorted((extracted / 'kitguard/static').rglob('*')):
        if path.is_file():
            url = '/static/' + path.relative_to(extracted / 'kitguard/static').as_posix()
            response = client.get(url)
            assert response.status_code == 200 and response.content == path.read_bytes(), url
            statuses[url] = response.status_code
    reports = {}
    for mode in ('main', 'detector', 'all'):
        response = client.get('/api/readiness', params={'mode': mode})
        assert response.status_code == 200
        report = response.json()
        assert report['schema'] == 'kitguard.readiness.v1' and report['mode'] == mode
        assert report['version'] == '0.6.0.dev2' and not report['ready']
        checks = {item['check']: item for item in report['checks']}
        assert checks['static_assets']['passed'] and checks['running_application_version']['passed']
        reports[mode] = {'ready': report['ready'], 'scopes': report['scopes']}
        statuses['/api/readiness?mode=' + mode] = response.status_code
    assert client.get('/api/readiness?mode=invalid').status_code == 422
    attachment = client.get('/api/readiness?mode=detector&download=true')
    assert attachment.status_code == 200 and attachment.json()['mode'] == 'detector'
    assert attachment.headers['content-disposition'].startswith('attachment; filename="kitguard-readiness-detector-')
    assert attachment.headers['cache-control'] == 'no-store'
    statuses['/api/readiness?mode=detector&download=true'] = attachment.status_code
    response = client.get('/api/detector-lab/status')
    assert response.status_code == 200 and response.json()['enabled'] is False
    statuses['/api/detector-lab/status'] = response.status_code
    # Prove routes exist through validation/404 responses; do not create fake participants or observations.
    assert client.post('/api/task-trials', json={}).status_code == 422
    assert client.get('/api/task-trials/missing').status_code == 422
    assert client.get('/api/task-trials/missing', headers={'X-Trial-Token': 'synthetic-invalid-token'}).status_code == 404
    assert client.get('/api/orders/missing/inspection-jobs').status_code == 404
    assert client.post('/api/orders/missing/inspection-jobs', json={}).status_code == 422
    assert client.post('/api/orders/missing/manual-review', json={}).status_code == 422
    assert client.post('/api/orders/missing/reopen', json={}).status_code == 422
    assert client.get('/api/orders').json() == {'orders': []}
    assert 'torch' not in sys.modules and 'mlx' not in sys.modules and 'mlx_vlm' not in sys.modules

print(json.dumps({'imported_from': kitguard.__file__, 'version': kitguard.__version__,
                  'http_200_and_exact_static_bytes': statuses, 'readiness_scopes': reports,
                  'task_trials_route_validation': 'passed', 'inspection_jobs_route_validation': 'passed',
                  'manual_review_route_validation': 'passed', 'orders_created': 0,
                  'torch_imported': False, 'mlx_imported': False, 'model_inference_executed': False}))
