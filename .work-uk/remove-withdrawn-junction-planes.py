from pathlib import Path
p=Path('server/ukvertical.py');text=p.read_text()
a=text.index('    def junction_plane(');b=text.index('    def aligned_endpoint(',a)
text=text[:a]+text[b:]
for line in ('        self.junction_planes={}\n','        self.end_geometry={}\n','        self.plan_junctions={}\n','        self.endpoint_profiles={}\n','        self.junction_profiles={}\n'):
 text=text.replace(line,'')
a=text.index('                for (fid,ids,ll),p,(_,sp) in zip(');b=text.index('                self.natural_ends[key]=rows',a)
text=text[:a]+'''                for (fid,ids,ll),p in zip(ends,plan_roads(self.frame,parts,self.raw)):
                    x,y,_=self.frame.geodetic_to_enu(ll[:,1],ll[:,0],0.)
                    for j,at in enumerate((0,-1)):rows.append((fid,ids[j],np.array([x[j],y[j]]),p.z[at]))
'''+text[b:]
p.write_text(text)
p=Path('server/tests/test_road_interfaces.py');text=p.read_text()
a=text.index(' def test_overlapping_junction_transitions_have_no_inner_radius_step(');b=text.index(' def test_submillimetre_source_segment',a)
text=text[:a]+text[b:]
old="  model.mainline_plans.update({('a',):a,('b',):b,('upper',):upper})\n"
new=old+"  from types import SimpleNamespace\n  for p in (a,b):model.plan_specs[p]=SimpleNamespace(profile=SimpleNamespace(mainline=False),width=12.)\n"
text=text.replace(old,new);p.write_text(text)
