"""Independent stdlib-only audit of fixed MANTA cross-source saved predictions.

No model loading, image decoding, or imports from producer/scoring code. Terminal
file binding is intentionally separate from the pure full-denominator scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import traceback
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

THRESHOLD = .9
OUTPUT_CLASSES = ('nut', 'yellow_green_washer')
IDENTITIES = ('nut', 'washer')
POPULATION = {'nut': 168, 'washer': 12, 'bolt': 399}
GROUP_CLASS = {
    ('screws_validation_collection', 'nut'): 156,
    ('screws_validation_collection', 'bolt'): 387,
    ('GOPR0183', 'nut'): 12,
    ('unprefixed_Washer', 'washer'): 12,
    ('GOPR0181', 'bolt'): 12,
}
METADATA_SHA = 'b6fe42c2520b19f7a24ccb1124600fe48a02430f0b7015752312316132f742ad'
CHECKPOINT_SHA = 'ea29bfcf33dcf680e1b3ac2afa26de366991d029a42a3b5fe7ef7a5be1b3f985'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require_number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'Non-finite/non-number')


def check_probability(row):
    """Recompute stable softmax; no tolerance is ever added to the .9 decision."""
    logits, probabilities = row['logits'], row['probabilities']
    require(isinstance(logits, list) and isinstance(probabilities, list)
            and len(logits) == len(probabilities) == 2, 'Two-class output required')
    for value in [*logits, *probabilities]:
        require_number(value)
    require(all(0 <= p <= 1 for p in probabilities), 'Probability outside [0,1]')
    exponentials = [math.exp(value-max(logits)) for value in logits]
    expected = [value/sum(exponentials) for value in exponentials]
    require(all(abs(actual-computed) <= 2e-6 for actual, computed in zip(probabilities, expected)),
            'Saved probability differs from logits softmax')
    return 0 if probabilities[0] >= probabilities[1] else 1


def check_record_metadata(records, full=True):
    require(isinstance(records, list) and records, 'Empty record list')
    identities = set()
    sources = {}
    for index, row in enumerate(records):
        require(row['index'] == index and row['input_id'] == f'roi-{index:04}', 'ROI sequence changed')
        identity = (row['source_id'], row['annotation_id'])
        require(identity not in identities, 'Duplicate author ROI')
        identities.add(identity)
        label = row['expected_identity']
        require(label in (*IDENTITIES, 'bolt'), 'Unplanned ground-truth identity')
        require(row['class_index'] == {'nut': 0, 'washer': 1, 'bolt': None}[label], 'Class index changed')
        require(row['score_role'] == ('open_category_bolt' if label == 'bolt' else 'nut_washer_identity'), 'Score role changed')
        require(type(row['tiny']) is bool and (row['author_aabb_clipped'] is None
                or type(row['author_aabb_clipped']) is bool), 'Invalid tiny/clipped metadata')
        box, size = row['aabb_xyxy'], row['image_size']
        require(len(box) == 4 and len(size) == 2 and all(type(v) is int and v > 0 for v in size), 'Invalid box/image shape')
        for value in box:
            require_number(value)
        x0, y0, x1, y1 = box
        require(x1 > x0 and y1 > y0, 'Empty annotation box')
        require(row['short_side'] == min(x1-x0, y1-y0) and row['tiny'] == (min(x1-x0, y1-y0) < 16), 'Tiny membership changed')
        rounded = [math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)]
        clipped = [max(0, min(limit, value)) for limit, value in zip([*size, *size], rounded)]
        require(clipped == row['crop_xyxy'] and row['integer_crop_clamped'] == (rounded != clipped), 'Fixed pixel crop changed')
        require(clipped[2] > clipped[0] and clipped[3] > clipped[1], 'Empty crop')
        signature = (row['source_group'], row['source_sha256'], tuple(size), row['image_index'])
        require(row['source_id'] not in sources or sources[row['source_id']] == signature, 'Source identity inconsistent')
        sources[row['source_id']] = signature
    if full:
        require(len(records) == 579 and len(sources) == 80, '579 targets / 80 source denominator required')
        require(Counter(r['expected_identity'] for r in records) == POPULATION, 'Class denominator changed')
        require(Counter((r['source_group'], r['expected_identity']) for r in records) == GROUP_CLASS, 'Source/class census changed')
        require(Counter((r['source_group'], r['expected_identity']) for r in records if r['tiny'])
                == {('unprefixed_Washer', 'washer'): 4, ('GOPR0181', 'bolt'): 4}, 'Tiny census changed')
        require(Counter(r['expected_identity'] for r in records if r['author_aabb_clipped'] is True)
                == {'nut': 1, 'bolt': 8}, 'Clipped census changed')
        require(sum(r['author_aabb_clipped'] is None for r in records) == 36, 'Unknown clipped census changed')
    return sources


def validate_raw(records, predictions):
    require(len(predictions) == len(records), 'Missing/extra prediction rows')
    for record, prediction in zip(records, predictions):
        require(prediction['input_id'] == record['input_id'], 'Prediction order/identity changed')
        require(prediction.get('input_sha256') == record.get('input_sha256'), 'Prepared input SHA changed')
        require(all(prediction[key] == record[key] for key in ('source_id', 'expected_identity', 'class_index',
                'source_group', 'tiny', 'author_aabb_clipped')), 'Raw metadata differs from frozen source')
        require(prediction['status'] in ('ok', 'failed', 'not_attempted'), 'Unknown prediction status')
        started, completed = prediction['actual_forward_started'], prediction['actual_forward_returned']
        require(type(started) is bool and type(completed) is bool and (not completed or started), 'Invalid actual-forward flags')
        if prediction['status'] == 'ok':
            require(prediction['error'] is None and started and completed, 'Successful row lacks completed forward')
            index = check_probability(prediction)
            require(prediction['model_output_class'] == OUTPUT_CLASSES[index], 'Recorded argmax class changed')
            require(prediction['threshold_result'] == ('accepted' if max(prediction['probabilities']) >= THRESHOLD else 'U'), 'Recorded threshold answer changed')
        elif prediction['status'] == 'failed':
            require(prediction['error'] is not None, 'Failure without error evidence')
        else:
            require(not started and not completed and prediction['logits'] is None
                    and prediction['probabilities'] is None, 'Unattempted row has model evidence')


def result_code(record, prediction, forced=False):
    """Failure status wins even if a partial output was preserved."""
    if prediction['status'] == 'failed':
        return 'E'
    if prediction['status'] == 'not_attempted':
        return 'N'
    index = check_probability(prediction)
    if not forced and max(prediction['probabilities']) < THRESHOLD:
        return 'U'
    if record['expected_identity'] == 'bolt':
        return 'accepted_' + IDENTITIES[index]
    return 'C' if index == record['class_index'] else 'W'


def count_panel(records, predictions, forced=False):
    main = [(r, p) for r, p in zip(records, predictions) if r['expected_identity'] != 'bolt']
    bolts = [(r, p) for r, p in zip(records, predictions) if r['expected_identity'] == 'bolt']
    result = {}
    for name, entries, categories in (
            ('identity', main, tuple('CWUEN')),
            ('bolt', bolts, ('accepted_nut', 'accepted_washer', 'U', 'E', 'N'))):
        counts = Counter(result_code(r, p, forced) for r, p in entries)
        denominator = len(entries)
        table = {'denominator': denominator, 'counts': {key: counts[key] for key in categories},
                 'source_images': len({r['source_id'] for r, _ in entries}),
                 'source_groups': len({r['source_group'] for r, _ in entries})}
        if name == 'identity':
            table['correct_coverage'] = counts['C']/denominator if denominator else None
            table['wrong_rate'] = counts['W']/denominator if denominator else None
            table['confusions'] = {
                'nut_to_washer': sum(r['expected_identity'] == 'nut' and result_code(r, p, forced) == 'W' for r, p in entries),
                'washer_to_nut': sum(r['expected_identity'] == 'washer' and result_code(r, p, forced) == 'W' for r, p in entries),
            }
        else:
            table['false_acceptances'] = counts['accepted_nut'] + counts['accepted_washer']
            table['false_acceptance_rate'] = table['false_acceptances']/denominator if denominator else None
            table['evaluated_fraction'] = (denominator-counts['E']-counts['N'])/denominator if denominator else None
        result[name] = table
    return result


def independent_score(records, predictions, full=True):
    check_record_metadata(records, full=full)
    validate_raw(records, predictions)
    result = {'threshold': THRESHOLD, 'threshold_0_9': count_panel(records, predictions),
              'forced_argmax': count_panel(records, predictions, forced=True)}
    dimensions = {
        'class': lambda r: r['expected_identity'],
        'source_group': lambda r: r['source_group'],
        'source_class': lambda r: (r['source_group'], r['expected_identity']),
        'tiny': lambda r: r['tiny'],
        'author_clipped': lambda r: r['author_aabb_clipped'],
        'source_class_tiny_clipped': lambda r: (r['source_group'], r['expected_identity'], r['tiny'], r['author_aabb_clipped']),
    }
    result['slices'] = {}
    for name, grouping in dimensions.items():
        groups = defaultdict(list)
        for r, p in zip(records, predictions):
            groups[json.dumps(grouping(r), ensure_ascii=False, separators=(',', ':'))].append((r, p))
        result['slices'][name] = {
            key: count_panel([r for r, _ in group], [p for _, p in group])
            for key, group in sorted(groups.items())}
    class_coverages = [cell['identity']['correct_coverage'] for cell in result['slices']['class'].values()
                       if cell['identity']['denominator']]
    source_coverages = [cell['identity']['correct_coverage'] for cell in result['slices']['source_class'].values()
                        if cell['identity']['denominator']]
    result['class_macro_correct_coverage'] = sum(class_coverages)/len(class_coverages) if class_coverages else None
    result['source_class_macro_correct_coverage'] = sum(source_coverages)/len(source_coverages) if source_coverages else None
    main_size = sum(r['expected_identity'] != 'bolt' for r in records)
    bolt_size = len(records)-main_size
    constants = {}
    for identity in IDENTITIES:
        correct = sum(r['expected_identity'] == identity for r in records)
        constants['constant_'+identity] = {
            'identity': {'denominator': main_size, 'counts': {'C': correct, 'W': main_size-correct, 'U': 0, 'E': 0, 'N': 0}},
            'bolt': {'denominator': bolt_size, 'accepted_nut': bolt_size if identity == 'nut' else 0,
                     'accepted_washer': bolt_size if identity == 'washer' else 0, 'U': 0, 'E': 0, 'N': 0},
        }
    constants['all_unknown'] = {
        'identity': {'denominator': main_size, 'counts': {'C': 0, 'W': 0, 'U': main_size, 'E': 0, 'N': 0}},
        'bolt': {'denominator': bolt_size, 'accepted_nut': 0, 'accepted_washer': 0, 'U': bolt_size, 'E': 0, 'N': 0},
    }
    result['analytic_baselines'] = constants
    result['production_promotion'] = False
    return result


def expected_group_keys(records, all_sources=None, is_bolt=False):
    groups = {'all': list(range(len(records)))}
    for index, row in enumerate(records):
        labels = {'source_group': row['source_group'], 'identity': row['expected_identity'],
                  'tiny': 'lt16' if row['tiny'] else 'ge16',
                  'author_clipped': 'unknown' if row['author_aabb_clipped'] is None else str(row['author_aabb_clipped']).lower()}
        names = [f'{key}={value}' for key, value in labels.items()]
        names.extend(('|'.join(f'{key}={labels[key]}' for key in ('source_group', 'identity')),
                      '|'.join(f'{key}={labels[key]}' for key in labels)))
        for name in names:
            groups.setdefault(name, []).append(index)
    for source in all_sources or sorted({r['source_group'] for r in records}):
        for identity in ('bolt',) if is_bolt else IDENTITIES:
            prefix = f'source_group={source}|identity={identity}'
            groups.setdefault(prefix, [])
            for tiny in ('lt16', 'ge16'):
                for clipped in ('true', 'false', 'unknown'):
                    groups.setdefault(prefix+f'|tiny={tiny}|author_clipped={clipped}', [])
    return groups


def verify_producer_analysis(records, predictions, saved):
    """Compare every producer slice to an independent subset calculation."""
    for panel, forced in (('threshold_0_9', False), ('forced_argmax', True)):
        for name, is_bolt in (('identity', False), ('bolt_open_category', True)):
            pairs = [(r, p) for r, p in zip(records, predictions) if (r['expected_identity'] == 'bolt') == is_bolt]
            rows, preds = [r for r, _ in pairs], [p for _, p in pairs]
            groups = expected_group_keys(rows, sorted({r['source_group'] for r in records}), is_bolt)
            require(set(saved[panel][name]) == set(groups), 'Missing/extra producer slice')
            for key, indices in groups.items():
                subset = [rows[i] for i in indices]
                table = count_panel(subset, [preds[i] for i in indices], forced)['bolt' if is_bolt else 'identity']
                observed = saved[panel][name][key]
                tally = dict(table['counts'])
                if is_bolt:
                    tally['accepted_yellow_green_washer'] = tally.pop('accepted_washer')
                require(observed['denominator'] == table['denominator'] and observed['counts'] == tally
                        and observed['image_count'] == table['source_images']
                        and observed['source_group_count'] == table['source_groups'], 'Producer slice counts differ: '+key)
                if not subset:
                    require(observed['status'] == 'not_applicable_no_targets', 'Empty slice not marked N/A')
                if is_bolt:
                    require(observed['false_acceptance_rate'] == table['false_acceptance_rate'], 'Producer false-acceptance rate differs')
                else:
                    require(observed['correct_coverage'] == table['correct_coverage']
                            and observed['coverage'] == ((tally['C']+tally['W'])/len(subset) if subset else None), 'Producer coverage differs')
                    columns = Counter()
                    for i in indices:
                        code = result_code(rows[i], preds[i], forced)
                        column = {'U': 'unknown', 'E': 'error', 'N': 'not_attempted'}.get(code)
                        if column is None:
                            column = OUTPUT_CLASSES[check_probability(preds[i])]
                        columns[column] += 1
                    require(observed['confusion'] == {k: columns[k] for k in (*OUTPUT_CLASSES, 'unknown', 'error', 'not_attempted')}, 'Producer confusion differs')
        # Macro rates are recomputed directly from the original pairs, including E/N.
        class_cells, source_cells = [], []
        for key_function, cells in ((lambda r: r['expected_identity'], class_cells),
                                    (lambda r: (r['source_group'], r['expected_identity']), source_cells)):
            grouped = defaultdict(list)
            for record, prediction in zip(records, predictions):
                if record['expected_identity'] != 'bolt':
                    grouped[key_function(record)].append(result_code(record, prediction, forced))
            cells.extend((codes.count('C')/len(codes), (codes.count('C')+codes.count('W'))/len(codes)) for codes in grouped.values())
        macros = saved[panel]['identity_macros']
        require(macros['class_count'] == len(class_cells) and macros['nonempty_source_class_cells'] == len(source_cells), 'Macro denominator differs')
        for prefix, cells in (('class', class_cells), ('source_class', source_cells)):
            for i, suffix in enumerate(('correct_coverage', 'coverage')):
                require(math.isclose(macros[prefix+'_macro_'+suffix], sum(c[i] for c in cells)/len(cells), abs_tol=1e-12, rel_tol=0), 'Macro score differs')
    n = sum(r['expected_identity'] != 'bolt' for r in records)
    b = len(records)-n
    expected = {}
    for index, label in enumerate(OUTPUT_CLASSES):
        c = sum(r['class_index'] == index for r in records)
        expected[label] = {'identity': {'C': c, 'W': n-c, 'U': 0, 'E': 0, 'N': 0, 'class_macro_correct_coverage': .5},
                           'bolt_open_category': {'accepted': b, 'U': 0, 'E': 0, 'N': 0, 'false_acceptance_rate': 1.0}}
    expected['abstain_all'] = {'identity': {'C': 0, 'W': 0, 'U': n, 'E': 0, 'N': 0, 'class_macro_correct_coverage': 0.0},
                               'bolt_open_category': {'accepted': 0, 'U': b, 'E': 0, 'N': 0, 'false_acceptance_rate': 0.0}}
    require(saved['constant_baselines'] == expected and saved['production_promotion'] is False, 'Analytic baseline/promotion differs')


def check_batches(records, predictions, batches, run):
    require(len(batches) <= 19, 'Repeated/extra forward batch')
    for index, batch in enumerate(batches):
        expected_rows = records[index*32:(index+1)*32]
        require(batch['index'] == index and batch['input_ids'] == [r['input_id'] for r in expected_rows], 'Batch order/partition changed')
        started, returned = batch['actual_forward_started'], batch['actual_forward_returned']
        require(type(started) is bool and type(returned) is bool and (not returned or started), 'Impossible batch flags')
        for prediction in predictions[index*32:(index+1)*32]:
            require(prediction['batch_index'] == index and prediction['actual_forward_started'] == started
                    and prediction['actual_forward_returned'] == returned, 'Row/batch actual-call flags differ')
        for field in ('wall_seconds', 'model_seconds', 'decode_tensor_seconds'):
            if batch[field] is not None:
                require_number(batch[field])
                require(batch[field] >= 0, 'Negative batch timing')
    require(all(p['status'] == 'not_attempted' for p in predictions[len(batches)*32:]), 'Unrecorded forward batch')
    for label in ('started', 'returned'):
        require(run['actual_forward_calls_'+label] == sum(b['actual_forward_'+label] for b in batches), 'Actual call total differs')
    for kind in ('model', 'decode_tensor'):
        require(run['timing'][kind+'_seconds'] == sum(b[kind+'_seconds'] or 0 for b in batches), 'Duplicate/missing timing total')
    if run['status'] == 'completed':
        require(len(batches) == 19 and all(p['status'] == 'ok' for p in predictions)
                and all(b['status'] == 'completed' and b['actual_forward_started'] and b['actual_forward_returned'] for b in batches), 'Completed run lacks 579 successes / 19 batches')


CONFIG = {'epoch': 10, 'device': 'mps', 'precision': 'float32', 'batch_size': 32, 'threshold': .9,
          'output_classes': ['nut', 'yellow_green_washer'], 'score_aliases': ['nut', 'washer'],
          'mean': [.485, .456, .406], 'std': [.229, .224, .225], 'augment': False, 'retries': 0,
          'planned_forward_calls': 19}


def audit(run_dir, plan_path, plan_sha, approval_path, approval_sha):
    """Only terminal saved files are read; all evidence hashes are returned."""
    run_dir, plan_path, approval_path = (Path(p).resolve() for p in (run_dir, plan_path, approval_path))
    bindings = {}

    def bound(path, expected=None):
        path = Path(path).resolve()
        actual = sha(path)
        require(expected is None or actual == expected, 'Hash mismatch: '+str(path))
        bindings[str(path)] = actual
        return path

    run = read(bound(run_dir/'run.json'))
    require(run['schema'] == 'kitguard.v08.manta-transfer.inference-run.v1'
            and run['status'] in ('completed', 'completed_with_failures', 'interrupted', 'failed')
            and run['final_integrity_passed'] is True, 'Nonterminal or failed-integrity run')
    require(run['planned_roi_count'] == 579 and run['planned_forward_calls'] == 19
            and run['training_steps'] == 0 and run['production_change'] is False, 'Scope changed')
    plan = read(bound(plan_path, plan_sha))
    approval = read(bound(approval_path, approval_sha))
    require(plan['schema'] == 'kitguard.v08.manta-transfer.inference-plan.v1' and plan['config'] == CONFIG, 'Frozen configuration changed')
    require(approval['schema'] == 'kitguard.v08.manta-transfer.inference-approval.v1'
            and approval['status'] == 'approved' and approval['authorized_by'] == 'root'
            and approval['scope'] == 'infer_all579_oracle_rois_once'
            and approval['allow_training'] is False and approval['production_change'] is False
            and approval['plan_sha256'] == run['plan_sha256'] == plan_sha
            and run['approval_sha256'] == approval_sha, 'Run/approval/plan mismatch')
    inventory = read(bound(run_dir/'artifact_inventory.json', run['artifact_inventory_sha256']))
    expected_files = {'plan.json', 'approval.json', 'started.json', 'raw.jsonl', 'predictions.json',
                      'batches.json', 'tensor_hashes.json', 'analysis.json'}
    require(set(inventory) == expected_files and {p.name for p in run_dir.iterdir()}
            == expected_files | {'artifact_inventory.json', 'run.json'}, 'Run artifact inventory changed')
    for name, receipt in inventory.items():
        path = bound(run_dir/name, receipt['sha256'])
        require(path.stat().st_size == receipt['bytes'], 'Artifact byte count differs')
    require(sha(run_dir/'plan.json') == plan_sha and sha(run_dir/'approval.json') == approval_sha, 'Run plan/approval copy differs')
    for rel, expected in plan['source_snapshot'].items():
        bound(plan_path.parent/'source_snapshot'/rel, expected)
    require(set(plan['source_snapshot']) == {'scripts/v08/run_manta_transfer.py', 'tests/test_manta_transfer_inference_v08.py',
                                            'docs/v0.8/MANTA_CLASSIFIER_CROSS_SOURCE_PROTOCOL_V1.md'}, 'Inference source inventory changed')
    require(approval['runner_sha256'] == plan['source_snapshot']['scripts/v08/run_manta_transfer.py'], 'Approved runner differs')
    bound(plan['factory_path'], '5f3475a5b911cada936eb62fae24890b1f4096153307a6b64a7e5619bca9057c')
    bound(plan['coco_path'], '907ea3f91ff92242bc1baea8049276a3e76bca48ce7560bd268cc029f37977b5')
    require(plan['classifier_checkpoint']['sha256'] == approval['classifier_checkpoint_sha256'] == CHECKPOINT_SHA, 'Different checkpoint selected')
    bound(plan['classifier_checkpoint']['path'], CHECKPOINT_SHA)
    internal = read(bound(plan['internal_audit']['path'], 'b9df04653db0e0ded4b6db2e0165e74508cc2c02a20829f98f25a5f1a9c57afd'))
    bound(plan['internal_run']['path'], '2985d6152377b9031d7fd067c2974952c03c35a6d1018957a2e74ea74abfd1e9')
    require(internal['status'] == 'passed' and internal['independent_results']['continuation_gate'] is True, 'Internal continuation gate failed')
    for path, expected in plan['runtime']['files'].items():
        bound(path, expected)
    meta = read(bound(plan['metadata_path'], METADATA_SHA))
    require(plan['metadata_sha256'] == METADATA_SHA, 'Different source selection')
    root = Path(plan['project_root'])
    expected_layout = {
        'test-results/v0.8-manta-transfer-root-check-v1/machine-check.json': '283b02f1221db6d6072a0f24c93c23e639df0cf3374ec6cd16e76b4eb9e6567a',
        'test-results/v0.8-manta-transfer-root-check-v1/visual-review.json': '6b349d01f0e61dfbf7ee50702f907d99f0bc92fcb88fcede02c820a0259a585c',
    }
    require(plan['layout_evidence'] == expected_layout, 'Different layout evidence')
    for rel, expected in expected_layout.items():
        require(read(bound(root/rel, expected))['preparation_sha256'] == plan['preparation_sha256'], 'Root reconstruction/layout evidence differs')
    for rel, expected in meta['bindings'].items():
        bound(root/rel, expected)
    for rel, expected in meta['source_snapshot'].items():
        bound(Path(plan['metadata_path']).parent/'source_snapshot'/rel, expected)
    for path, expected in meta['runtime']['files'].items():
        bound(path, expected)
    prep = read(bound(plan['preparation_path'], plan['preparation_sha256']))
    base = Path(plan['input_base'])
    require(base == Path(plan['preparation_path']).parent and prep['status'] == 'prepared'
            and prep['status_counts'] == {'prepared': 579} and prep['metadata_sha256'] == METADATA_SHA
            and prep['models_called'] == 0 and prep['integrity_error'] is None, 'Preparation incomplete')
    bound(base/'metadata.json', METADATA_SHA)
    bound(base/'approval.json', prep['approval_sha256'])
    records = read(bound(base/'records.json', prep['records_sha256']))
    require(records == plan['records'] and len(records) == len(meta['records']) == 579, 'Prepared plan population changed')
    check_record_metadata(records)
    for record, original in zip(records, meta['records']):
        require(all(record.get(key) == value for key, value in original.items())
                and record['status'] == 'prepared' and record['error'] is None, 'Preparation metadata drift')
        require(record['input_path'] == f"inputs/{record['input_id']}.png" and record['input_size'] == [224, 224], 'Input path/shape changed')
        bound(base/record['input_path'], record['input_sha256'])
    for image in meta['images']:
        bound(root/image['source_path'], image['source_sha256'])
    # Predictions are read only after terminal, provenance and population checks.
    predictions = read(run_dir/'predictions.json')
    raw = [json.loads(line) for line in (run_dir/'raw.jsonl').read_text().splitlines()]
    require(raw == predictions, 'Raw JSONL and final predictions differ')
    require(dict(Counter(p['status'] for p in predictions)) == run['status_counts'], 'Run status counts differ')
    result = independent_score(records, predictions)
    hashes = read(run_dir/'tensor_hashes.json')
    require(set(hashes) <= {r['input_id'] for r in records}
            and all(isinstance(value, str) and len(value) == 64 and set(value) <= set('0123456789abcdef') for value in hashes.values()), 'Invalid tensor hash receipt')
    require({p['input_id'] for p in predictions if p['status'] == 'ok'} <= set(hashes), 'Missing successful input tensor receipt')
    batches = read(run_dir/'batches.json')
    require(set(hashes) <= {input_id for batch in batches for input_id in batch['input_ids']}, 'Tensor receipt beyond attempted batches')
    require({input_id for batch in batches if batch['actual_forward_started'] for input_id in batch['input_ids']} <= set(hashes), 'Started forward missing tensor receipts')
    if run['status'] == 'completed':
        fingerprint = run['model_state_sha256']
        require(len(hashes) == 579 and run['model_state_unchanged'] is True
                and isinstance(fingerprint, str) and len(fingerprint) == 64
                and set(fingerprint) <= set('0123456789abcdef'), 'Incomplete tensor / unchanged-model receipts')
    check_batches(records, predictions, batches, run)
    verify_producer_analysis(records, predictions, read(run_dir/'analysis.json'))
    require(all(sha(path) == expected for path, expected in bindings.items()), 'Evidence changed during audit')
    return {'schema': 'kitguard.v08.manta-transfer.independent-audit.v1', 'status': 'passed',
            'audited_at_utc': datetime.now(UTC).isoformat(), 'auditor_sha256': sha(__file__), 'bindings': bindings,
            'planned_targets': 579, 'source_images': 80, 'independent_results': result,
            'recorded_runtime': {'status': run['status'], 'actual_forward_calls_started': run['actual_forward_calls_started'],
                                 'actual_forward_calls_returned': run['actual_forward_calls_returned'], 'timing': run['timing']},
            'new_model_calls': 0, 'images_decoded': 0, 'production_promotion': False,
            'limitations': ['Byte hashes only: no image/tensor reconstruction or model replay in this audit.',
                            'Saved runtime and state-unchanged flags are historical receipts, not new measurements.',
                            'Oracle AABBs may contain neighboring targets/background; bolt acceptance is not pure-bolt classification error.',
                            'Previously exposed validation ROIs are correlated within source images; no physical holdout claim.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'plan', 'approval', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('--expected-approval-sha256', required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Audit output already exists')
    try:
        result = audit(args.run, args.plan, args.expected_plan_sha256, args.approval, args.expected_approval_sha256)
    except Exception as error:  # noqa: BLE001 -- preserve first failure without changing producer artifacts
        result = {'schema': 'kitguard.v08.manta-transfer.independent-audit.v1', 'status': 'failed',
                  'auditor_sha256': sha(__file__), 'error': {'type': type(error).__name__, 'message': str(error)},
                  'traceback': traceback.format_exc(), 'new_model_calls': 0, 'images_decoded': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output), 'sha256': sha(args.output)}))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
