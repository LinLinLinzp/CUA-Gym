"""Exercise the exact production hook against persisted first and revised uploads."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys

source=Path(__file__).parent
path=source.parents[1]/'runtime/sitehost/hx01_artwork_review.py'
spec=importlib.util.spec_from_file_location('hook',path)
hook=importlib.util.module_from_spec(spec);spec.loader.exec_module(hook)
build=Path(sys.argv[1]); target=Path(sys.argv[2]);target.mkdir(parents=True,exist_ok=False)
first=build/'variants/unrepaired_review'; final=build/'variants/golden'
shutil.copytree(first/'files',target/'files')
for site in ('wordpress_com','pinterest'):
    dest=target/'state'/site;dest.mkdir(parents=True)
    shutil.copy(first/'state'/site/'current.json',dest/'current.json')
baseline=json.loads((build/'seed/asana.json').read_text())
proposed=deepcopy(baseline)
proposed['comments'].append(dict(commentId='request-one',taskId=hook.TASK,userId='user-dana',content='Review https://wordpress.com/preview/post/post-tide-marks-gallery and https://www.pinterest.com/pin/p-tide-marks-release'))
reviewed=hook.apply_review(target,'asana',baseline,proposed,'2026-11-19T14:30:00Z')
assert reviewed['artworkReviews'][-1]['result']=='changes_requested'
assert len(reviewed['attachments'])==4
stale=hook.apply_review(target,'asana',reviewed,deepcopy(baseline),'2026-11-19T14:31:00Z')
assert stale['artworkReviews']==reviewed['artworkReviews']
assert len(stale['attachments'])==4
shutil.copytree(final/'files',target/'files',dirs_exist_ok=True)
for site in ('wordpress_com','pinterest'):
    shutil.copy(final/'state'/site/'current.json',target/'state'/site/'current.json')
proposed=deepcopy(reviewed)
proposed['comments'].append(dict(commentId='request-two',taskId=hook.TASK,userId='user-dana',content='Recheck https://wordpress.com/preview/post/post-tide-marks-gallery and https://www.pinterest.com/pin/p-tide-marks-release'))
accepted=hook.apply_review(target,'asana',reviewed,proposed,'2026-11-19T14:40:00Z')
assert accepted['artworkReviews'][-1]['result']=='accepted',accepted['artworkReviews'][-1]
assert len(list((target/'files/asana/review').glob('*.png')))==4
changed=deepcopy(accepted)
wp_path=target/'state/wordpress_com/current.json';wp=json.loads(wp_path.read_text())
ps_path=target/'state/pinterest/current.json';ps=json.loads(ps_path.read_text())
if baseline['artworkReviewChannel']=='wordpress_com':
    pin=next(p for p in ps['pins'] if p['id']=='p-tide-marks-release');pin['image']=pin['image'].replace('pin19_','copy_')
    old=target/'files/pinterest/fixture/pin19_tide-marks-pin.png';shutil.copy(old,old.with_name('copy_tide-marks-pin.png'));ps_path.write_text(json.dumps(ps))
else:
    wp['media'][-1]['id']='replacement-accepted-media';wp['posts'][0]['featuredImageId']='replacement-accepted-media';wp_path.write_text(json.dumps(wp))
changed['comments'].append(dict(commentId='request-three',taskId=hook.TASK,userId='user-dana',content='Recheck https://wordpress.com/ and https://www.pinterest.com/'))
rejected=hook.apply_review(target,'asana',accepted,changed,'2026-11-19T14:50:00Z')
assert rejected['artworkReviews'][-1]['result']=='changes_requested'
(target/'hook-report.json').write_text(json.dumps(dict(first='changes_requested',second='accepted',changed_accepted='changes_requested',stale_preserved=True,viewport_files=4),indent=2)+'\n')
print('PASS actual uploads -> reject -> revised acceptance; stale and accepted-identity guards')
