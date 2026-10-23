exec(open('.work-uk/divider-route.py').read().split('tiles=set()')[0])
x,y,_=fr.geodetic_to_enu(53.05787,-1.26216,0.)
for fid,sp,ln,_ in rr:
 d,q,t=ukroadside._nearest_many(np.array([[x,y]]),ln)
 if d[0]<50:print(fid,sp.profile.forward,sp.profile.drive,sp.profile.offset,'d',d,'point',q,'ends',ln[[0,-1],:2],'t',t)
md.close()
