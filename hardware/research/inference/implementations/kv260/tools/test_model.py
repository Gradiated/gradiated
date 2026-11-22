"""Model, fixture and creative-material contracts without importing MLX."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generative
import model
import runtime


class ModelContract(unittest.TestCase):
    def changed(self, name, mutate, renew=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in generative.DATA.iterdir():
                if path.is_file():
                    (root/path.name).write_bytes(path.read_bytes())
            obj=json.loads((root/name).read_text())
            mutate(obj)
            (root/name).write_text(json.dumps(obj))
            if renew:
                meta=json.loads((root/'selection.json').read_text())
                meta['files_sha256'][name]=runtime.sha(root/name)
                (root/'selection.json').write_text(json.dumps(meta))
            with patch.object(generative,'DATA',root):
                with self.assertRaises(ValueError):generative.inputs()

    def test_bos_only_and_every_byte_supervised(self):
        meta,rows=generative.inputs()
        self.assertEqual(meta['parameters'],26720)
        seq=[model.sequence(r) for r in rows]
        self.assertEqual(sum(len(s)-1 for s in seq),4535)
        self.assertEqual(max(map(len,seq)),143)
        for row,s in zip(rows,seq):
            self.assertEqual(s,[256,*row['text'].encode(),257])
            self.assertTrue(all(0<=t<256 for t in s[1:-1]))

    def test_changed_target_is_rejected(self):
        self.changed('jokes.json',lambda rows:rows[0].update(text='A replacement.'))

    def test_geometry_and_recipe_cannot_change_silently(self):
        self.changed('selection.json',lambda p:p['configuration'].update(hidden_size=64))
        self.changed('selection.json',lambda p:p['recipe'].update(temperature=2))
        self.changed('selection.json',lambda p:p['training'].update(passes=3))

    def test_input_manifest_path_escape_is_rejected(self):
        self.changed('selection.json',lambda p:p['files_sha256'].update({'../outside':'0'*64}))

    def test_duplicate_and_truncated_corpus_rejected_even_with_renewed_pin(self):
        self.changed('jokes.json',lambda rows:rows[1].update(text=rows[0]['text']),True)
        self.changed('jokes.json',lambda rows:rows[0].update(text='x'*300),True)

    def test_grade_keeps_failures_and_repeated_text(self):
        _,rows=generative.inputs()
        texts=[rows[0]['text'],rows[0]['text'],'A failure.']
        result=model.grade({'results':[dict(text=t,eos=True,valid_utf8_bytes=True) for t in texts]},rows)
        self.assertEqual((result['exact'],result['unique_exact'],result['largest_joke_count']),(2,1,2))
        self.assertEqual([v['text'] for v in result['results']],texts)

    def test_eos_and_valid_bytes_required(self):
        _,rows=generative.inputs()
        entries=[dict(text=rows[0]['text'],eos=e,valid_utf8_bytes=v) for e,v in [(False,True),(True,False),(True,True)]]
        self.assertEqual(model.grade({'results':entries},rows)['exact'],1)

    def test_gate_covers_variety_completeness_and_repetition(self):
        good=dict(samples=64,exact=60,unique_exact=20,largest_joke_count=10,completed=64)
        self.assertTrue(model.qualifies(good))
        for k,v in [('samples',63),('exact',59),('unique_exact',19),('largest_joke_count',11),('completed',63)]:
            self.assertFalse(model.qualifies(dict(good,**{k:v})))

    def test_text_seed_is_stable_and_case_sensitive(self):
        self.assertEqual(generative.text_seed('hello'),int.from_bytes(hashlib.sha256(b'hello').digest()[:4],'little')&0x7fffffff)
        self.assertNotEqual(generative.text_seed('hello'),generative.text_seed('HELLO'))

    def test_complete_original_fixtures_include_gibberish(self):
        _,rows=generative.inputs()
        fixtures=[json.loads(line) for line in (generative.DATA/'expected.jsonl').read_text().splitlines()]
        self.assertEqual([r['seed'] for r in fixtures],list(range(10001,10129)))
        for row in fixtures:
            self.assertEqual(model.decode(row['tokens']),(row['text'],row['valid_utf8_bytes']))
        graded=model.grade({'results':fixtures},rows)
        self.assertEqual((graded['exact'],graded['unique_exact'],graded['largest_joke_count']),(127,41,8))
        self.assertIsNone(fixtures[124]['matched_joke'])
        self.assertIn('hdddrroatomatsed',fixtures[124]['text'])

    def test_payload_pin_checked_before_loading(self):
        meta,_=generative.inputs()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'models/tiny/q8';path.mkdir(parents=True)
            source=generative.R/'models/tiny/q8'
            for name in ('config.json','model.safetensors'):(path/name).write_bytes((source/name).read_bytes())
            with patch.object(generative,'R',root),patch.object(model,'loaded',return_value='sentinel') as loader:
                self.assertEqual(generative.load_selected(meta),'sentinel')
                (path/'model.safetensors').write_bytes(b'changed')
                with self.assertRaises(ValueError):generative.load_selected(meta)
                self.assertEqual(loader.call_count,1)

    def test_payload_path_escape_is_rejected(self):
        meta,_=generative.inputs();meta=copy.deepcopy(meta)
        meta['weights']['q8']['path']='../outside'
        with patch.object(model,'loaded') as loader:
            with self.assertRaises(ValueError):generative.load_selected(meta)
            loader.assert_not_called()

    def test_terminal_controls_are_escaped(self):
        rendered=model.terminal('hello\x1b]52;c;value\x07\r')
        self.assertFalse(any(ord(c)<32 or 127<=ord(c)<160 for c in rendered))
        self.assertIn('\\u001b',rendered)


class MaterialContract(unittest.TestCase):
    def test_library_deduplication_and_provenance(self):
        material=runtime.PROJECT/'material'
        index=runtime.read(material/'library-index.json')
        self.assertEqual(runtime.sha(material/'library.jsonl'),index['library_sha256'])
        records=[json.loads(line) for line in (material/'library.jsonl').read_text().splitlines()]
        self.assertEqual(len(records),index['unique_records'])
        by_id={r['id']:r for r in records}
        self.assertEqual(len(by_id),len(records))
        for record in records:
            encoded=json.dumps(record['content'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
            self.assertEqual(hashlib.sha256(encoded).hexdigest(),record['id'])
            self.assertTrue(record['sources'])
        for source in index['source_files']:
            self.assertTrue(all(r in by_id for r in source['records']))
        self.assertEqual(len(index['source_files']),227)

    def test_all_banked_joke_versions_have_a_readable_copy(self):
        material=runtime.PROJECT/'material'
        catalogue=(material/'joke-library.txt').read_text()
        records=[json.loads(line) for line in (material/'library.jsonl').read_text().splitlines()]
        texts={r['content']['text'] for r in records if isinstance(r['content'],dict)
               and isinstance(r['content'].get('text'),str)
               and any(Path(s['path']).name in ('jokes.json','bank.jsonl') for s in r['sources'])}
        self.assertEqual(len(texts),106)
        for text in texts:self.assertIn(text,catalogue)


class RTLContract(unittest.TestCase):
    def test_nearest_even_signed_ties_and_limits(self):
        import rtl
        for value,expected in ((-5,-2),(-3,-2),(-1,0),(1,0),(3,2),(5,2)):
            self.assertEqual(rtl.oracle([value]+[0]*31,[16384]+[0]*31)['result'],expected)
        for value in (-16385,-16383,16383,16385):
            self.assertEqual(rtl.oracle([1]+[0]*31,[value]+[0]*31)['result'],round(value/32768))
        positive=rtl.oracle([-32768]*32,[-32768]*32)
        negative=rtl.oracle([-32768]*32,[32767]*32)
        self.assertEqual((positive['sum'],positive['result'],positive['saturated']),(2**35,32767,1))
        self.assertEqual((negative['result'],negative['saturated']),(-32768,1))

    def test_invalid_operand_geometry_and_range_rejected(self):
        import rtl
        for x,w in (([0]*31,[0]*32),([32768]*32,[0]*32),([0]*32,[-32769]*32)):
            with self.assertRaises(ValueError):rtl.oracle(x,w)

    def test_real_fixture_and_repeatable_case_generation(self):
        import rtl
        a=rtl.fixtures();b=rtl.fixtures()
        self.assertEqual(a,b)
        self.assertEqual(len(a),150)
        self.assertEqual((a[0]['expected']['sum'],a[0]['expected']['result'],a[0]['expected']['saturated']),(-3760136,-115,0))
        self.assertTrue(any(c['expected']['saturated'] for c in a))

    def test_matrix_rows_have_distinct_orientation_and_validate_geometry(self):
        import rtl
        x=list(range(1,33))
        weights=[[32767 if j==31-r else 0 for j in range(32)] for r in range(32)]
        case=rtl.matrix_case('Reversed identity',x,weights)
        self.assertEqual([e['result'] for e in case['expected']],list(range(32,0,-1)))
        with self.assertRaises(ValueError):rtl.matrix_case('Bad rows',x,weights[:2])
        weights[0]=weights[0][:-1]
        with self.assertRaises(ValueError):rtl.matrix_case('Bad columns',x,weights)

    def test_qkv_layout_uses_correct_bank_scales_and_rejects_wrong_shift(self):
        import rtl
        manifest=runtime.read(runtime.MODEL/'fixed.json')
        layout=rtl.projection_layout(manifest,96)
        self.assertEqual([(p['name'],p['start'],p['count']) for p in layout],[('Q',0,32),('K',32,32),('V',64,32)])
        self.assertEqual([(p['accumulator_exponent'],p['output_exponent']) for p in layout],[(-26,-11),(-26,-11),(-27,-12)])
        manifest['activation_exponents']['v']=-11
        with self.assertRaisesRegex(ValueError,'shift of 15'):rtl.projection_layout(manifest,96)

    def test_qkv_banks_have_distinct_expected_values(self):
        import rtl
        x=list(range(1,33))
        weights=[[scale if j==r else 0 for j in range(32)] for scale in (32767,-32768,16384) for r in range(32)]
        case=rtl.matrix_case('Distinct Q K V',x,weights)
        self.assertEqual([v['result'] for v in case['expected']],x+[-v for v in x]+[round(v/2) for v in x])
        self.assertEqual(rtl.reset_probe_count(96),8)

    def test_rope_split_half_order_and_signed_rotations(self):
        import rtl
        x=list(range(-32,32))
        identity=rtl.rope_case('Identity',x,[[16384,0]]*8,0)
        self.assertEqual(identity['outputs'],x)
        quarter=rtl.rope_case('Quarter',x,[[0,16384]]*8,255)
        expected=[]
        for base in range(0,64,16):expected += [-v for v in x[base+8:base+16]]+x[base:base+8]
        self.assertEqual(quarter['outputs'],expected)
        self.assertEqual([(e['index_a'],e['index_b']) for e in identity['expected']],
                         [(base+j,base+j+8) for base in (0,16,32,48) for j in range(8)])

    def test_rope_signed_ties_clipping_and_validation(self):
        import rtl
        for value,expected in ((-5,-2),(-3,-2),(-1,0),(1,0),(3,2),(5,2)):
            case=rtl.rope_case('Tie',[value]*64,[[8192,0]]*8,1)
            self.assertEqual(case['outputs'],[expected]*64)
        clipped=rtl.rope_case('Clip',[-32768]*64,[[-32768,32767]]*8,255)
        self.assertTrue(any(e['saturated'] for e in clipped['expected']))
        for x,coefficients,position in (([0]*63,[[0,0]]*8,0),([32768]*64,[[0,0]]*8,0),
                ([0]*64,[[32768,0]]*8,0),([0]*64,[[0,0]]*7,0),([0]*64,[[0,0]]*8,256)):
            with self.assertRaises(ValueError):rtl.rope_case('Invalid',x,coefficients,position)
        a=rtl.rope_synthetic_fixtures()
        self.assertEqual(a,rtl.rope_synthetic_fixtures())
        self.assertTrue(any(e['saturated'] for c in a for e in c['expected']))

    def test_rope_rejects_changed_precision(self):
        import rtl
        manifest=runtime.read(runtime.MODEL/'fixed.json')
        self.assertEqual(rtl.rope_layout(manifest)['coefficient_exponent'],-14)
        manifest['activation_exponents']['qrot']=-12
        with self.assertRaises(ValueError):rtl.rope_layout(manifest)

    def test_rope_trace_rejects_corruption_wrong_pairing_and_missing_request(self):
        import csv
        import rtl
        case=rtl.rope_case('Zero',[0]*64,[[16384,0]]*8,1)
        rows=[]
        for label in range(11):
            for pair,e in enumerate(case['expected']):
                base=label*300+pair*7
                common=dict(case=label,position=1,busy=1,pair=pair,index_a=e['index_a'],index_b=e['index_b'],
                    result_a=0,result_b=0,saturated=0,step_valid=0,step_pair=pair,step_kind=0,
                    step_input=0,step_coefficient=0,step_product=0,step_total=0,a=0,b=0,cosine=16384,sine=0,
                    combined_a=0,combined_b=0,result_valid=0)
                rows.append(dict(common,cycle=base,phase=1))
                for j in range(4):rows.append(dict(common,cycle=base+j+2,phase=j+3,step_valid=1,step_kind=j,
                                                   step_coefficient=[16384,0,16384,0][j]))
                rows.append(dict(common,cycle=base+6,phase=7,result_valid=1))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rope.csv'
            def write(records):
                with path.open('w',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(records)
            write(rows);checks,_=rtl.check_rope_trace(path,[case])
            self.assertEqual((checks['outputs_checked'],checks['products_checked']),(704,1408))
            rows[1]['step_product']=1;write(rows)
            with self.assertRaisesRegex(ValueError,'product/combined'):rtl.check_rope_trace(path,[case])
            rows[1]['step_product']=0;rows[5]['index_b']=7;write(rows)
            with self.assertRaisesRegex(ValueError,'rounding/clipping/tag'):rtl.check_rope_trace(path,[case])
            rows[5]['index_b']=8;write([r for r in rows if r['case']!=10])
            with self.assertRaisesRegex(ValueError,'Missing completed'):rtl.check_rope_trace(path,[case])

    def test_matrix_trace_rejects_missing_or_wrong_row_tags(self):
        import csv
        import rtl
        case=rtl.matrix_case('Zeros',[0]*32,[[0]*32 for _ in range(32)])
        fields=('case','cycle','phase','row','step_row','result_row','step_valid','step_index',
                'operand_x','operand_w','step_product','step_sum','accumulator','result_valid','result','saturated')
        rows=[]
        for label in range(8):
            for r in range(32):
                def add(**values):rows.append(dict.fromkeys(fields,0)|dict(case=label,row=r,step_row=r,result_row=r,**values))
                base=label*3000+r*68
                add(cycle=base,phase=1)
                for i in range(32):add(cycle=base+2+2*i,phase=1,step_valid=1,step_index=i)
                add(cycle=base+65,phase=4,result_valid=1)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cycles.csv'
            def write():
                with path.open('w') as stream:
                    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
            write();self.assertEqual(rtl.check_trace(path,[case])[0]['terms_checked'],8192)
            rows[33]['result_row']=1;write()
            with self.assertRaisesRegex(ValueError,'result row'):rtl.check_trace(path,[case])
            rows[33]['result_row']=0;rows[1]['step_row']=31;write()
            with self.assertRaisesRegex(ValueError,'32 observed terms'):rtl.check_trace(path,[case])

    def test_changed_toolchain_manifest_rejected(self):
        import rtl
        with patch.object(rtl,'PIN_SHA256','0'*64):
            with self.assertRaisesRegex(ValueError,'pin changed'):rtl.tool_pin()

    def test_observed_trace_corruption_is_rejected(self):
        import csv
        import rtl
        case={'x':[0]*32,'w':[0]*32,'expected':rtl.oracle([0]*32,[0]*32)}
        fields=('case','cycle','phase','step_valid','step_index','operand_x','operand_w',
                'step_product','step_sum','accumulator','result_valid','result','saturated')
        rows=[]
        for label in range(7):
            def add(**values):rows.append(dict.fromkeys(fields,0)|dict(case=label,**values))
            add(cycle=label*100,phase=1)
            for i in range(32):add(cycle=label*100+2+2*i,phase=1,step_valid=1,step_index=i)
            add(cycle=label*100+65,phase=4,result_valid=1)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cycles.csv'
            def write():
                with path.open('w') as stream:
                    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
            write();self.assertEqual(rtl.check_trace(path,[case])[0]['terms_checked'],224)
            rows[1]['step_product']=1;write()
            with self.assertRaisesRegex(ValueError,'product/sum mismatch'):rtl.check_trace(path,[case])
            rows[1]['step_product']=0;rows[33]['result']=1;write()
            with self.assertRaisesRegex(ValueError,'rounding/saturation mismatch'):rtl.check_trace(path,[case])


class VivadoContract(unittest.TestCase):
    def test_clock_audit_preserves_unused_ps_outputs_but_rejects_loads_and_waivers(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);ps='tiny_ps_axi_i/ps/PS8_i';buffer='tiny_ps_axi_i/ps/BUFG_PS_i'
            domain=dict(design_top='tiny_ps_axi_wrapper',clock_domain='clk_pl_0',clock_period_ns='20.000',
                sealed_expected_derived_clock_hz='49999500',ps8=ps,source_pin=ps+'/PLCLK[0]',buffer=buffer,
                buffer_input=buffer+'/I',buffer_output=buffer+'/O',neural_aclk='tiny_ps_axi_i/neural/aclk',
                clock_gap_nets='0',neural_clock_pins='1')
            def save_domain():
                (folder/'clock-domain.tsv').write_text(''.join(f'{k}\t{v}\n' for k,v in domain.items())+
                    'neural_clock_pin\ttiny_ps_axi_i/neural/example/C\n')
            save_domain()
            coverage='native_no_clock\t1\nunconstrained_internal_endpoints\t0\nunused_ps_clock_outputs\t1\nunclocked_active_pins\t0\n'
            (folder/'clock-coverage.tsv').write_text(coverage+f'ps_clock_output\t{ps}/EMIOENET0MDIOMDC\tOUT\t0\n')
            constraints='default_rules 6444\nchanged_rules 0\nwaiver_objects 0\nloop_allow_nets 0\nclock_route_overrides 0\n'
            for n in ('constraints-before.txt','constraints-after.txt'):(folder/n).write_text(constraints)
            metrics=dict(native_no_clock='1',unused_ps_clock_outputs='1',unclocked_active_pins='0',unconstrained_internal_endpoints='0')
            clocks=[dict(name='clk_pl_0',period_ns=20.0)];checks=dict(no_clock=1,unconstrained_internal_endpoints=0)
            result=rtl.board_clock_audit(folder,metrics,clocks,checks)
            self.assertEqual(result['native_no_clock'],1)
            self.assertEqual(result['active_unclocked_pins'],0)
            (folder/'clock-coverage.tsv').write_text(coverage+f'ps_clock_output\t{ps}/EMIOENET0MDIOMDC\tOUT\t1\n')
            with self.assertRaisesRegex(ValueError,'coverage is incomplete'):
                rtl.board_clock_audit(folder,metrics,clocks,checks)
            (folder/'clock-coverage.tsv').write_text(coverage+f'ps_clock_output\t{ps}/EMIOENET0MDIOMDC\tOUT\t0\n')
            domain['clock_period_ns']='10.000';save_domain()
            with self.assertRaisesRegex(ValueError,'20 ns target differs'):
                rtl.board_clock_audit(folder,metrics,clocks,checks)
            domain['clock_period_ns']='20.000';save_domain()
            (folder/'constraints-after.txt').write_text(constraints.replace('waiver_objects 0','waiver_objects 1'))
            with self.assertRaisesRegex(ValueError,'waiver audit differs'):
                rtl.board_clock_audit(folder,metrics,clocks,checks)

    def test_board_predecessor_seals_nested_sources_and_rejects_unrelated_input(self):
        import rtl
        names=('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','axi_transformer')
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);project=folder/'project/candidate.xpr';project.parent.mkdir()
            project.write_bytes(b'Synthetic project identity; never opened by Vivado')
            source=folder/'project/generated/dependency.v';source.parent.mkdir();source.write_text('original')
            artifacts={str(p.relative_to(folder)):dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in (project,source)}
            report=dict(state='complete',mode='board-prep',blocks={'board-prep':dict(state='complete',logical_design_validated=True,
                source_sha256={'rtl/'+n+'.sv':runtime.sha(rtl.RTL/(n+'.sv')) for n in names},artifacts=artifacts)})
            path=folder/'results.json';runtime.save(path,report);digest=runtime.sha(path)
            with patch.object(runtime,'RUNTIME',folder):
                result=rtl.board_predecessor(path,digest,'generate',project,runtime.sha(project),{})
                self.assertEqual(result['phase'],'board-prep')
                unrelated=folder/'unrelated.xpr';unrelated.write_bytes(project.read_bytes())
                with self.assertRaisesRegex(ValueError,'not a sealed predecessor'):
                    rtl.board_predecessor(path,digest,'generate',unrelated,runtime.sha(unrelated),{})
                source.write_text('changed')
                with self.assertRaisesRegex(ValueError,'artifact/closure changed'):
                    rtl.board_predecessor(path,digest,'generate',project,runtime.sha(project),{})

    def test_full_board_budget_cannot_extend_simulator_deadline(self):
        import subprocess
        import sys
        result=subprocess.run([sys.executable,'-B',str(runtime.PROJECT/'tools/rtl.py'),
            '--vivado','transformer','--board-build-timeout','600'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2)
        self.assertIn('only applies to synth/opt/place/route',result.stderr)

    def test_whole_model_hashes_are_checked_before_reference_array_decode(self):
        import fixed
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);path=folder/'transfer.json';path.write_text('{')
            with patch.object(rtl,'fixed_tensor_values',side_effect=AssertionError('must not load before seal')):
                with self.assertRaisesRegex(ValueError,'manifest hash'):
                    rtl.mac_whole_model_reference(folder,'0'*64)
            names=('BOS','J01-first16','authored128','repeated-J01-256')
            files={'goldens.json','export-results.json'}|{'provenance/'+name+'/'+n for name in names
                for n in ('export-results.json','watchdog.json','launch.json')}
            pins={}
            for name in files:
                item=folder/name;item.parent.mkdir(parents=True,exist_ok=True);item.write_text('{}')
                pins[name]=dict(bytes=item.stat().st_size,sha256=runtime.sha(item))
            transfer=dict(schema=1,kind='fresh-selected-fixed-whole-model-reference',case_names=list(names),
                case_lengths=[1,16,128,256],files=pins,fixed_manifest_sha256=fixed.SELECTED_SHA256,
                fixed_payload_sha256='1'*64)
            runtime.save(path,transfer);(folder/'goldens.json').write_text('{')
            with patch.object(rtl,'fixed_tensor_values',return_value=({},dict(images=dict(sha256='1'*64)))):
                with self.assertRaisesRegex(ValueError,'input bytes/hash'):
                    rtl.mac_whole_model_reference(folder,runtime.sha(path))

    def test_saved_trace_requires_current_sources_and_actual_simulation_receipts(self):
        import rtl
        names=('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','transformer_tb')
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);path=folder/'results.json'
            sources={n:runtime.sha(rtl.RTL/(n+'.sv')) for n in names}
            report=dict(state='complete',mode='transformer',commands=[],blocks=dict(transformer=dict(state='complete',source_sha256=sources)))
            with patch.object(runtime,'RUNTIME',folder):
                sources['transformer']='0'*64;runtime.save(path,report)
                with self.assertRaisesRegex(ValueError,'not current'):
                    rtl.verified_transformer_trace(path,runtime.sha(path),[])
                sources['transformer']=runtime.sha(rtl.RTL/'transformer.sv');runtime.save(path,report)
                with self.assertRaisesRegex(ValueError,'simulation/cleanup'):
                    rtl.verified_transformer_trace(path,runtime.sha(path),[])

    def test_resource_report_accepts_synthesis_and_placed_lut_labels(self):
        import rtl
        rows=[('CLB Registers','10084','234240','4.30'),('Block RAM Tile','36.5','144','25.35'),
              ('RAMB36/FIFO*','30','144','20.83'),('RAMB18','13','288','4.51'),
              ('DSPs','10','1248','0.80'),('URAM','0','64','0.00')]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'utilization.rpt'
            for label in ('CLB LUTs*','CLB LUTs'):
                path.write_text(''.join(f'| {n} | {used} | 0 | 0 | {available} | {percent} |\n'
                    for n,used,available,percent in [(label,'30682','117120','26.20'),*rows]))
                values=rtl.synthesis_utilization(path)
                self.assertEqual(values['luts']['used'],30682)
                self.assertEqual(values['bram_tiles']['used'],36.5)
                self.assertEqual(values['dsps']['used'],10)

    def test_routed_diagnostic_rejects_timing_drc_and_incomplete_routes(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            metrics=dict(setup_slack_ns='1.0',hold_slack_ns='0.1',drc_errors_or_critical_warnings='0',
                fully_placed='1',fully_routed='1',routing_errors='0',unrouted_nets='0',
                partially_routed_nets='0',clock_period_ns='20.000',clock_source='BUFGCE_X0Y0')
            (folder/'timing.rpt').write_text('All user specified timing constraints are met.\n')
            def check(changes):
                values=dict(metrics,**changes)
                (folder/'metrics.txt').write_text(''.join(f'{k} {v}\n' for k,v in values.items()))
                with patch.object(rtl,'synthesis_utilization',return_value={}):
                    return rtl.implementation_report_result(folder,'PASS IMPLEMENTATION REPORTS',20,'BUFGCE_X0Y0')
            self.assertTrue(check({})['diagnostic_passed'])
            for changes in ({'setup_slack_ns':'-0.1'},{'hold_slack_ns':'-0.1'},
                {'drc_errors_or_critical_warnings':'1'},{'fully_routed':'0'},
                {'routing_errors':'1'},{'unrouted_nets':'1'},{'partially_routed_nets':'1'}):
                self.assertFalse(check(changes)['diagnostic_passed'])
            (folder/'timing.rpt').write_text('Pulse-width constraint failed.\n')
            self.assertFalse(check({})['diagnostic_passed'])
            with self.assertRaisesRegex(ValueError,'clock assumptions'):
                check({'clock_period_ns':'10.000'})

    def test_mac_arrays_keep_causal_heads_cache_positions_and_integer_bounds(self):
        import copy
        import rtl
        widths={name:32 for name in ('embed','norm1','q','k','v','qrot','krot','context',
                'o','res1','norm2','down','res2','normfinal')}
        widths.update(gate=128,up=128,silu=128,hidden=128,logits=320)
        states={name:dict(shape=[1,2,width],dtype='int64',values=[[[0]*width for _ in range(2)]])
                for name,width in widths.items()}
        states['scores']=dict(shape=[1,2,2,2],dtype='int64',values=[[[[11,999],[12,13]],[[21,999],[22,23]]]])
        states['prob']=dict(shape=[1,2,2,2],dtype='int64',values=[[[[32768,0],[10000,22768]],[[32768,0],[16000,16768]]]])
        caches={name:dict(shape=[1,2,2,16],dtype='int64',values=[[[[0]*16 for _ in range(2)] for _ in range(2)]]) for name in ('k','v')}
        case=dict(tokens=[256,76],states=states,cache=caches,incremental_matches_full=True)
        tokens,golden=rtl.mac_case_golden(case)
        self.assertEqual(tokens,[256,76])
        self.assertEqual(golden[0]['scores'],{0:11,256:21})
        self.assertEqual(golden[1]['scores'],{0:12,1:13,256:22,257:23})
        self.assertEqual(set(golden[1]['cache_k']),set(range(32,64)))
        wrong=copy.deepcopy(case);wrong['cache']['k']['values'][0][1][1][2]=1
        with self.assertRaisesRegex(ValueError,'final cache differs'):
            rtl.mac_case_golden(wrong)
        wrong=copy.deepcopy(case);wrong['states']['logits']['values'][0][0][0]=1<<31
        with self.assertRaisesRegex(ValueError,'value/range'):
            rtl.mac_case_golden(wrong)
        wrong=copy.deepcopy(case);del wrong['states']['hidden']
        with self.assertRaisesRegex(ValueError,'inventory'):
            rtl.mac_case_golden(wrong)

    def test_implementation_budget_cannot_extend_simulator_deadline(self):
        import subprocess
        import sys
        result=subprocess.run([sys.executable,'-B',str(runtime.PROJECT/'tools/rtl.py'),
            '--vivado','transformer','--implementation-timeout','600'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2)
        self.assertIn('only for core-only opt/place/route',result.stderr)

    def test_implementation_rejects_unsealed_report_changed_rtl_and_corrupt_checkpoint(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);work=folder/'transformer';work.mkdir()
            checkpoint=work/'synthesized.dcp'
            checkpoint.write_bytes(b'Synthetic digest test only; never passed to Vivado')
            names=('fixed_scalar','rmsnorm','mac32','qk_rope','kv_cache','frontend',
                   'attention','dense','feedforward','transformer')
            source_pins={'rtl/'+name+'.sv':runtime.sha(rtl.RTL/(name+'.sv')) for name in names}
            report=dict(state='complete',mode='synthesis',blocks=dict(transformer=dict(
                state='complete',top='transformer',target='xck26-sfvc784-2LV-c',source_sha256=source_pins,
                artifacts={'synthesized.dcp':dict(bytes=checkpoint.stat().st_size,sha256=runtime.sha(checkpoint))})))
            path=folder/'results.json'
            def seal():
                runtime.save(path,report)
                return runtime.sha(path)
            digest=seal()
            with patch.object(runtime,'RUNTIME',folder):
                with self.assertRaisesRegex(ValueError,'location/hash'):
                    rtl.implementation_checkpoint(path,'0'*64)
                source_pins['rtl/transformer.sv']='0'*64
                with self.assertRaisesRegex(ValueError,'RTL differs'):
                    rtl.implementation_checkpoint(path,seal())
                source_pins['rtl/transformer.sv']=runtime.sha(rtl.RTL/'transformer.sv')
                digest=seal();checkpoint.write_bytes(bytes(checkpoint.stat().st_size))
                with self.assertRaisesRegex(ValueError,'checkpoint bytes/hash'):
                    rtl.implementation_checkpoint(path,digest)

    def test_long_synthesis_budget_cannot_be_used_for_simulation(self):
        import subprocess
        import sys
        result=subprocess.run([sys.executable,'-B',str(runtime.PROJECT/'tools/rtl.py'),
            '--vivado','transformer','--synthesis-timeout','600'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2)
        self.assertIn('only for the complete transformer netlist',result.stderr)

    def test_model_loader_preserves_selected_word_bits_and_frozen_prefix(self):
        import rtl
        values,_=rtl.fixed_tensor_values();words=rtl.transformer_model_words(values)
        self.assertEqual(len(words),29281)
        self.assertEqual(words[:10240],[v&65535 for v in values['E']])
        self.assertEqual(words[-256:],values['rsqrt_table'])
        self.assertEqual(words[-513:-256],values['exp_table'])
        self.assertEqual(rtl.transformer_prefix_tokens('j01-3'),[256,76,105])

    def test_integer_tensor_digest_is_checked_before_header_decode(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);image=root/'models/tiny/fixed/fixed-tensors.safetensors'
            image.parent.mkdir(parents=True)
            image.write_bytes(bytes(64648))
            with patch.object(runtime,'RUNTIME',root):
                with self.assertRaisesRegex(ValueError,'integer payload changed'):
                    rtl.fixed_tensor_values()

    def test_synthesis_warning_collection_still_rejects_critical_warnings(self):
        import sys
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            commands=[]
            with self.assertRaisesRegex(RuntimeError,'failed'):
                rtl.vivado_command(Path(directory),'synthesis',[sys.executable,'-c',
                    'print("CRITICAL WARNING: injected unsupported construct")'],commands,allow_warnings=True)
            self.assertEqual(commands[0]['exit_code'],0)
            self.assertTrue(commands[0]['process_group_absent'])

    def test_zero_exit_with_fatal_or_hdl_warning_is_rejected_and_child_reaped(self):
        import sys
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            for message in ('Fatal: injected HDL failure','WARNING: injected HDL width warning'):
                commands=[]
                with self.assertRaisesRegex(RuntimeError,'failed'):
                    rtl.vivado_command(folder,'probe',[sys.executable,'-c',f'print({message!r})'],commands)
                self.assertEqual(commands[0]['exit_code'],0)
                self.assertTrue(commands[0]['child_reaped'])
                self.assertTrue(commands[0]['process_group_absent'])

    def test_frozen_transfer_rejects_corruption_and_changed_reference_source(self):
        import fixed
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            fixture=rtl.matrix_synthetic_fixtures(1)[:1]
            runtime.save(folder/'fixtures.json',fixture)
            source_names=('model/fixed.json','tools/fixed.py','rtl/mac32.sv','rtl/mac32_tb.sv')
            original=dict(accepted=True,rtl=dict(state='complete',artifacts={
                'fixtures.json':dict(sha256=runtime.sha(folder/'fixtures.json'))}),
                source_sha256={n:runtime.sha(runtime.PROJECT/n) for n in source_names})
            runtime.save(folder/'results.json',original)
            transfer=dict(schema=1,block='mac32',rows=1,fixed_manifest_sha256=fixed.SELECTED_SHA256,
                fixed_payload_sha256=runtime.read(runtime.MODEL/'fixed.json')['images']['sha256'],
                files={n:dict(bytes=(folder/n).stat().st_size,sha256=runtime.sha(folder/n))
                       for n in ('fixtures.json','results.json')})
            def seal():
                runtime.save(folder/'transfer.json',transfer)
                return runtime.sha(folder/'transfer.json')
            digest=seal()
            self.assertEqual(rtl.vivado_frozen(folder,digest,'mac32',1)[0],fixture)
            with self.assertRaisesRegex(ValueError,'manifest hash'):
                rtl.vivado_frozen(folder,'0'*64,'mac32',1)
            (folder/'fixtures.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'input hash'):
                rtl.vivado_frozen(folder,digest,'mac32',1)
            runtime.save(folder/'fixtures.json',fixture)
            original['source_sha256']['tools/fixed.py']='0'*64
            runtime.save(folder/'results.json',original)
            transfer['files']['results.json']=dict(bytes=(folder/'results.json').stat().st_size,
                                                   sha256=runtime.sha(folder/'results.json'))
            with self.assertRaisesRegex(ValueError,'Mac source differs'):
                rtl.vivado_frozen(folder,seal(),'mac32',1)

    def test_fixture_expected_values_are_independently_checked_before_simulation(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            cases=rtl.matrix_synthetic_fixtures(96)[:1]
            cases[0]['expected'][0]['result']+=1
            with self.assertRaisesRegex(ValueError,'oracle differs'):
                rtl.vivado_inputs(folder,'mac32',cases)
            cases=rtl.rope_synthetic_fixtures()[:1]
            cases[0]['outputs'][0]+=1
            with self.assertRaisesRegex(ValueError,'oracle differs'):
                rtl.vivado_inputs(folder,'qk_rope',cases)


class ImportedFixedContract(unittest.TestCase):
    """Transport inputs require explicit pins and the unchanged circuit arithmetic."""

    def fixture(self, folder):
        selected = json.loads((runtime.MODEL / 'fixed.json').read_text())
        image = runtime.RUNTIME / selected['runtime_path'] / selected['images']['file']
        manifest = copy.deepcopy(selected)
        for key in ('runtime_path', 'source_q8_sha256', 'study', 'teaching_projection'):
            manifest.pop(key, None)
        path = folder / 'arithmetic.json'
        path.write_text(json.dumps(manifest))
        return path, runtime.sha(path), image, manifest

    def test_explicit_transport_matches_original_words_without_selection_changes(self):
        import rtl
        original, _ = rtl.fixed_tensor_values()
        with tempfile.TemporaryDirectory() as directory:
            path, digest, image, manifest = self.fixture(Path(directory))
            values, actual = rtl.fixed_tensor_values(path, digest, image)
        self.assertEqual(actual, manifest)
        self.assertEqual(rtl.transformer_model_words(values), rtl.transformer_model_words(original))

    def test_manifest_pin_and_complete_explicit_arguments_are_required(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            path, digest, image, _ = self.fixture(Path(directory))
            for args in ((path, None, image), (None, digest, image), (path, digest, None),
                         (path, '0' * 64, image)):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    rtl.fixed_tensor_values(*args)

    def test_renewed_manifest_cannot_change_exponents_arithmetic_or_inventory(self):
        import rtl
        mutations = (
            lambda m: m['weight_exponents'].update(down=-15),
            lambda m: m['activation_exponents'].update(hidden=-10),
            lambda m: m.update(rounding='truncate'),
            lambda m: m.update(rsqrt_iterations=1),
            lambda m: m['images']['arrays']['down'].update(shape=[128, 32]),
            lambda m: m['images'].update(file='../escape.safetensors'),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as directory:
                path, _, image, manifest = self.fixture(Path(directory))
                mutate(manifest)
                path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, 'original circuit'):
                    rtl.fixed_tensor_values(path, runtime.sha(path), image)

    def test_external_tensor_hash_is_checked_before_decode(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest, _, manifest = self.fixture(root)
            image = root / 'fixed-tensors.safetensors'
            image.write_bytes(bytes(manifest['images']['bytes']))
            with self.assertRaisesRegex(ValueError, 'integer payload changed'):
                rtl.fixed_tensor_values(path, digest, image)

    def test_explicit_inputs_cannot_enter_a_build_or_legacy_simulation(self):
        import subprocess
        import sys
        for mode in ('board-build', 'transformer'):
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, '-B', str(runtime.PROJECT / 'tools/rtl.py'),
                    '--vivado', mode, '--fixed-inputs', 'arithmetic.json', '0' * 64,
                    'fixed-tensors.safetensors'], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn('only to pack transport', result.stderr)

    def test_imported_simulation_requires_fresh_goldens_before_any_model_load(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'fresh full-model goldens'):
                rtl.run_transformer_vivado(Path(directory), lambda *args: self.fail('tool invoked'),
                    model_inputs=('missing-arithmetic.json', '0' * 64, 'missing-tensors.safetensors'))

    def test_conditioned_reference_requires_trusted_seal_before_loading_weights(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'transfer.json').write_text('{}')
            with patch.object(rtl, 'fixed_tensor_values') as loader:
                for digest in ('0' * 64, rtl.CONDITIONED_TRANSFER_SHA256):
                    with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, 'manifest hash'):
                        rtl.mac_conditioned_reference(root, digest, ('unused', 'unused', 'unused'))
                loader.assert_not_called()

    def test_pack_records_explicit_manifest_and_exact_legacy_transport(self):
        import rtl
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, digest, image, manifest = self.fixture(root)
            original = root / 'original'
            imported = root / 'imported'
            original.mkdir()
            imported.mkdir()
            rtl.pack_model_words(original)
            result = rtl.pack_model_words(imported, model_inputs=(path, digest, image))
            self.assertEqual((imported / 'model-words.bin').read_bytes(),
                             (original / 'model-words.bin').read_bytes())
            self.assertEqual(result['package']['fixed_manifest_sha256'], digest)
            self.assertEqual(result['package']['fixed_tensor_image_sha256'], manifest['images']['sha256'])


class CacheContract(unittest.TestCase):
    def signals(self,**changes):
        return dict(dict(reset=0,write_valid=0,write_position=0,write_coordinate=0,write_k=0,write_v=0,
                         read_valid=0,read_position=0,read_coordinate=0,output_ready=0),**changes)

    def test_cache_addresses_and_selected_units(self):
        import rtl
        self.assertEqual({rtl.cache_address(p,c) for p in range(256) for c in range(32)},set(range(8192)))
        self.assertEqual(rtl.cache_address(255,31),8191)
        for p,c in ((256,0),(-1,0),(0,32),(0,-1)):
            with self.assertRaises(ValueError):rtl.cache_address(p,c)
        manifest=runtime.read(runtime.MODEL/'fixed.json')
        self.assertEqual(rtl.cache_layout(manifest)['logical_bytes'],32768)
        manifest['activation_exponents']['v']=-11
        with self.assertRaises(ValueError):rtl.cache_layout(manifest)

    def test_partial_visibility_backpressure_and_reset(self):
        import rtl
        ref=rtl.CacheReference()
        for c in range(31):
            result=ref.step(self.signals(write_valid=1,write_coordinate=c,write_k=c-16,write_v=32767-c))
            self.assertEqual(result['token_count'],0)
        self.assertEqual(ref.step(self.signals(read_valid=1))['read_fire'],0)
        self.assertEqual(ref.step(self.signals(write_valid=1,write_coordinate=0))['write_fire'],0)
        result=ref.step(self.signals(write_valid=1,write_coordinate=31,write_k=15,write_v=32736))
        self.assertEqual((result['token_count'],result['commit_valid']),(1,1))
        result=ref.step(self.signals(read_valid=1,read_coordinate=31))
        self.assertEqual((result['read_fire'],result['output_k'],result['output_v']),(1,15,32736))
        stalled=ref.step(self.signals(write_valid=1,write_position=1,read_valid=1))
        self.assertEqual((stalled['write_fire'],stalled['read_fire'],stalled['output_k']),(0,0,15))
        self.assertEqual(ref.step(self.signals(output_ready=1))['output_valid'],0)
        reset=ref.step(self.signals(reset=1,write_valid=1))
        self.assertEqual((reset['token_count'],reset['next_coordinate'],reset['output_valid']),(0,0,0))
        self.assertEqual(ref.memory[31],[15,32736])
        self.assertEqual(ref.step(self.signals(read_valid=1,read_coordinate=31))['read_fire'],0)

    def test_full_capacity_does_not_wrap(self):
        import rtl
        ref=rtl.CacheReference()
        for p in range(256):
            for c in range(32):ref.step(self.signals(write_valid=1,write_position=p,write_coordinate=c,
                                                    write_k=p*32+c-4096,write_v=4096-p*32-c))
        self.assertEqual(ref.count,256)
        for p in (0,255,256,511):
            self.assertEqual(ref.step(self.signals(write_valid=1,write_position=p))['write_fire'],0)
        out=ref.step(self.signals(read_valid=1,read_position=255,read_coordinate=31))
        self.assertEqual((out['output_position'],out['output_coordinate'],out['output_k'],out['output_v']),(255,31,4095,-4095))
        ref.step(self.signals(reset=1));self.assertEqual(ref.count,0)
        self.assertEqual(len(ref.memory),8192)

    def test_cache_trace_checker_rejects_modified_records_and_truncation(self):
        import rtl
        initial=self.signals(reset=1)
        observed=dict(initial,cycle=0,**rtl.CacheReference().step(initial))
        rtl.CacheReference().check(observed)
        for field in ('token_count','write_fire','output_k','output_valid'):
            changed=dict(observed);changed[field]+=1
            with self.assertRaisesRegex(ValueError,'protocol/value'):rtl.CacheReference().check(changed)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'empty.csv';path.write_text('cycle,bank\n')
            with self.assertRaisesRegex(ValueError,'Missing full-cache'):rtl.check_cache_trace(path,[{}, {}, {}])


class FixedScalarOracle(unittest.TestCase):
    def test_teaching_policy_preserves_other_quality_and_arithmetic_gates(self):
        import fixed
        numerical={'passed':False,'by_operation':{'logits':{'worst_normalized_RMSE':.0056}}}
        stats={'q':{'saturated':0}}
        self.assertFalse(fixed.accepts(True,numerical,stats,'strict'))
        self.assertTrue(fixed.accepts(True,numerical,stats,'teaching'))
        self.assertFalse(fixed.accepts(False,numerical,stats,'teaching'))
        self.assertFalse(fixed.accepts(True,numerical,{'q':{'saturated':1}},'teaching'))
        changed=copy.deepcopy(numerical)
        changed['by_operation']['logits']['worst_normalized_RMSE']=.0101
        self.assertFalse(fixed.accepts(True,changed,stats,'teaching'))
        with self.assertRaises(ValueError):fixed.accepts(True,numerical,stats,'unknown')

    def test_rounding_matches_independent_fraction_ties_even(self):
        from fractions import Fraction
        from fixed import scalar_rne
        for denominator in (1,2,3,4,8,127,32768):
            for numerator in (-2**45,-65,-9,-7,-5,-3,-1,0,1,3,5,7,9,65,2**45):
                self.assertEqual(scalar_rne(numerator,denominator),round(Fraction(numerator,denominator)))

    def test_changed_fixed_manifest_is_rejected_before_dependency_import(self):
        import fixed
        from unittest.mock import patch
        with patch.object(fixed,'SELECTED_SHA256','0'*64), patch.object(fixed,'dependencies',side_effect=AssertionError('must not import')):
            with self.assertRaisesRegex(ValueError,'manifest changed'):fixed.selected({})

    def test_changed_arithmetic_is_rejected_before_dependency_import(self):
        import fixed
        from unittest.mock import patch
        with patch.object(fixed,'implementation_sha256',return_value='0'*64), patch.object(fixed,'dependencies',side_effect=AssertionError('must not import')):
            with self.assertRaisesRegex(ValueError,'implementation changed'):fixed.selected({})

    def test_changed_fixed_payload_is_rejected_before_dependency_import(self):
        import fixed
        import generative
        import runtime
        from unittest.mock import patch
        meta,_ = generative.inputs()
        with patch.object(fixed,'dependencies',side_effect=AssertionError('must not import')):
            with patch.object(runtime,'sha',side_effect=[fixed.SELECTED_SHA256,'0'*64]):
                with self.assertRaisesRegex(ValueError,'modified fixed'):fixed.selected(meta)

    def test_nonpositive_denominators_are_rejected(self):
        from fixed import scalar_rne
        for denominator in (0,-1):
            with self.assertRaises(ValueError):scalar_rne(1,denominator)




class ConditionedContract(unittest.TestCase):
    def test_actual_utf8_input_and_fixed_boundary(self):
        self.assertEqual(model.conditioned_prefix('fu2p2q'),[256,*b'fu2p2q',258])
        self.assertEqual(model.conditioned_prefix('🍟'),[256,*'🍟'.encode(),258])
        self.assertEqual(model.conditioned_prefix(''),[256,258])
        self.assertEqual(len(model.conditioned_prefix('x'*96)),98)
        with self.assertRaises(ValueError):model.conditioned_prefix('x'*97)
        with self.assertRaises(ValueError):model.conditioned_prefix('🍟'*25)

    def test_only_answer_and_eos_supervised(self):
        x,y,mask=model.conditioned_example('abc','Hi')
        self.assertEqual(len(x),255)
        self.assertEqual(x[:7],[256,97,98,99,258,72,105])
        self.assertEqual(y[:7],[97,98,99,258,72,105,257])
        self.assertEqual(mask[:8],[0,0,0,0,1,1,1,0])
        self.assertEqual(sum(mask),3)
        self.assertTrue(all(v==0 for v in mask[7:]))

    def test_disjoint_corpus_and_all_jokes(self):
        _,jokes=generative.inputs()
        corpus=model.conditioned_corpus(jokes)
        sets=[{r['input'] for r in corpus[s]} for s in ('train','development','final')]
        self.assertEqual(len(corpus['final']),1000)
        self.assertFalse(sets[0]&sets[1] or sets[0]&sets[2] or sets[1]&sets[2])
        self.assertIn('fu2p2q',sets[2]);self.assertIn('',sets[2])
        self.assertEqual({r['independent_target'] for r in corpus['train']},{r['text'] for r in jokes})
        for part in ('train','development','final'):
            self.assertEqual(len(corpus[part]),len(sets[('train','development','final').index(part)]))
            for row in corpus[part]:model.conditioned_prefix(row['input'])

    def test_candidate_path_cannot_leave_runtime(self):
        with self.assertRaises(ValueError):generative.experiment_path(Path('/private/tmp/elsewhere'))


class RoleInputContract(unittest.TestCase):
    def test_utf8_bytes_roundtrip_without_loss(self):
        for text in ('fu2p2q','🍟','日本語','', ''.join(chr(i) for i in range(32,80))):
            tokens=model.conditioned_prefix(text,False,'role48')[1:]
            raw=bytes((tokens[i]-260)*48+tokens[i+1]-272 for i in range(0,len(tokens),2))
            self.assertEqual(raw,text.encode())
            self.assertTrue(all(260<=t<320 for t in tokens))
        with self.assertRaises(ValueError):model.conditioned_prefix('x'*49,False,'role48')

    def test_maximum_training_example_still_fits(self):
        _,jokes=generative.inputs()
        for row in jokes:
            x,y,m=model.conditioned_example('x'*48,row['text'],False,'role48')
            self.assertEqual(len(x),255)
            self.assertEqual(sum(m),len(row['text'].encode())+1)


class HexInputContract(unittest.TestCase):
    def test_hex_roundtrip_and_limit(self):
        for text in ('fu2p2q','日本語','🍟','', '\x00\t\n', 'x'*48):
            t=model.conditioned_prefix(text,False,'hex')[1:]
            self.assertTrue(all(272<=a<288 and 288<=b<304 for a,b in zip(t[::2],t[1::2])))
            self.assertEqual(bytes(((a-272)<<4)+(b-288) for a,b in zip(t[::2],t[1::2])),text.encode())
        with self.assertRaises(ValueError):model.conditioned_prefix('x'*49,False,'hex')
        with self.assertRaises(ValueError):model.conditioned_prefix('🍟'*13,False,'hex')

    def test_input_not_supervised_answer_and_eos_are(self):
        x,y,m=model.conditioned_example('a','Hi',False,'hex')
        self.assertEqual(x[:5],[256,278,289,72,105])
        self.assertEqual(y[:5],[278,289,72,105,257])
        self.assertEqual(m[:6],[0,0,1,1,1,0])


class ConditionedSelectionContract(unittest.TestCase):
    def test_frozen_hex_corpus_reproducible(self):
        _,jokes=generative.inputs()
        payload=(json.dumps(model.conditioned_corpus(jokes,'hex'),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
        selected=runtime.read(generative.DATA/'conditioned.json')
        self.assertEqual(hashlib.sha256(payload).hexdigest(),selected['corpus']['sha256'])

    def test_selection_pins_are_checked(self):
        selected=runtime.read(generative.DATA/'conditioned.json')
        self.assertTrue(generative.conditioned_pin(selected['fp32'],'candidate.json').is_dir())
        changed=dict(selected['fp32'],sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'hash differs'):generative.conditioned_pin(changed,'candidate.json')
        changed=dict(selected['fp32'],runtime_path='../outside')
        with self.assertRaises(ValueError):generative.conditioned_pin(changed,'candidate.json')

    def test_interactive_text_is_forwarded_without_seed_and_each_request_bounded(self):
        import sys
        with patch.object(sys,'argv',['generative.py','conditioned-chat']),patch('builtins.input',side_effect=['  fu2p2q  ',EOFError]),patch.object(runtime,'supervise',return_value=0) as run:
            generative.main()
        argv,timeout=run.call_args.args
        self.assertEqual(timeout,180)
        self.assertEqual(json.loads(argv[argv.index('--text-json')+1]),'  fu2p2q  ')
        self.assertNotIn('--seed',argv)


if __name__=='__main__':unittest.main()
