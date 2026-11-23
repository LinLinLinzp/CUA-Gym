"""Task-scoped upload-bound curator placement receipts for HX01.
Called under sitehost's write lock; only opt-in Asana state is transformed.
"""
import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlsplit
from PIL import Image, ImageDraw, ImageChops, ImageStat

TASK = 'task-tide-marks-release'

def asset(var_dir, site, url):
    if not isinstance(url, str): return None
    if url.startswith('data:image/png;base64,'):
        try:return base64.b64decode(url.split(',',1)[1],validate=True)
        except ValueError:return None
    parts=unquote(urlsplit(url).path).split('/')
    if len(parts)!=4 or parts[1]!='files' or any(x in ('.','..') for x in parts[2:]):return None
    for root in (Path(var_dir)/'files'/site,Path(var_dir)/'uploads'/site):
        path=root/parts[2]/parts[3]
        if path.is_file() and path.stat().st_size<30*1024*1024:return path.read_bytes()
    return None

def apply_review(var_dir, site, current, proposed, now):
    if site!='asana' or not isinstance(proposed,dict):return proposed
    # Server-authored reviews cannot be erased by a stale open Asana tab.
    reviews=current.get('artworkReviews',[])
    proposed['artworkReviews']=reviews
    for field,key in (('comments','commentId'),('attachments','attachmentId')):
        incoming={r.get(key) for r in proposed.get(field,[])}
        proposed.setdefault(field,[]).extend(r for r in current.get(field,[]) if str(r.get(key,'')).startswith('hx01-') and r.get(key) not in incoming)
    old={r.get('commentId') for r in current.get('comments',[])}
    requests=[r for r in proposed.get('comments',[]) if r.get('commentId') not in old and r.get('taskId')==TASK and r.get('userId')=='user-dana' and 'wordpress.com' in r.get('content','') and 'pinterest.com' in r.get('content','')]
    if not requests:return proposed
    try:
        wp=json.loads((Path(var_dir)/'state/wordpress_com/current.json').read_text())
        ps=json.loads((Path(var_dir)/'state/pinterest/current.json').read_text())
        post=next(x for x in wp['posts'] if x['id']=='post-tide-marks-gallery')
        media=next(x for x in wp['media'] if x['id']==post.get('featuredImageId'))
        pins=[x for x in ps['pins'] if x.get('title')=='Tide Marks: An Indoor Print Exhibition' and x.get('userId')==ps['currentUser']['id'] and x.get('id') not in {'p-gallery-0','p-gallery-1','p-gallery-2'}]
        if len(pins)!=1:return proposed
        pin=pins[0]; wb=asset(var_dir,'wordpress_com',media['url']); pb=asset(var_dir,'pinterest',pin['image'])
        if not wb or not pb:return proposed
        wi=Image.open(BytesIO(wb)).convert('RGB'); pi=Image.open(BytesIO(pb)).convert('RGB')
        if wi.size!=(1200,630) or pi.size!=(800,1200):return proposed
    except (OSError,ValueError,KeyError,StopIteration):return proposed
    rejected=current.get('artworkReviewChannel','wordpress_com')
    number=len(reviews)+1
    hashes=(hashlib.sha256(wb).hexdigest(),hashlib.sha256(pb).hexdigest())
    # In the 1200x440 centered feature viewport, R17's footer is clipped.
    # Compare the relocated credit pixels with the first actual upload; final grading checks all source layers.
    repaired=False
    if reviews:
        channel='wordpress_com' if rejected=='wordpress_com' else 'pinterest'
        old_url=reviews[0]['wordpressUrl' if channel=='wordpress_com' else 'pinterestUrl']
        old_bytes=asset(var_dir,channel,old_url)
        if old_bytes:
            old_image=Image.open(BytesIO(old_bytes)).convert('RGB')
            box=(471,587,1011,618) if channel=='wordpress_com' else (206,791,746,822)
            dx,dy=(-400,-480) if channel=='wordpress_com' else (0,-580)
            target=wi if channel=='wordpress_com' else pi
            expected=old_image.crop(box)
            for ox in range(-12,13):
                for oy in range(-12,13):
                    actual=target.crop((box[0]+dx+ox,box[1]+dy+oy,box[2]+dx+ox,box[3]+dy+oy))
                    if sum(ImageStat.Stat(ImageChops.difference(actual,expected)).mean)/3<4:
                        repaired=True
                        break
                if repaired:break
    unchanged=not reviews or ((pin['id']==reviews[0]['pinterestPinId'] and pin['image']==reviews[0]['pinterestUrl'] and hashes[1]==reviews[0]['pinterestSha256']) if rejected=='wordpress_com' else (media['id']==reviews[0]['wordpressMediaId'] and media['url']==reviews[0]['wordpressUrl'] and hashes[0]==reviews[0]['wordpressSha256']))
    accepted=bool(reviews and repaired and unchanged)
    receipt=dict(taskId=TASK,round=number,rejectedChannel=rejected,wordpressMediaId=media['id'],wordpressUrl=media['url'],wordpressSha256=hashes[0],pinterestPinId=pin['id'],pinterestUrl=pin['image'],pinterestSha256=hashes[1],result='accepted' if accepted else 'changes_requested')
    proposed['artworkReviews']=[*reviews,receipt]
    attachment_ids=[]
    for label,image,box in [('WordPress',wi,(0,95,1200,535) if rejected=='wordpress_com' else (0,0,1200,630)),('Pinterest',pi,(0,0,800,1200) if rejected=='wordpress_com' else (0,0,800,700))]:
        visible=image.crop(box); visible.thumbnail((900,900))
        screenshot=Image.new('RGB',(max(920,visible.width+40),visible.height+100),'#ffffff');d=ImageDraw.Draw(screenshot)
        d.text((20,15),f'{label} placement / review {number} / asset '+(media['id'] if label=='WordPress' else pin['id']),fill='#222222')
        screenshot.paste(visible,(20,60));out=BytesIO();screenshot.save(out,format='PNG');raw=out.getvalue()
        aid=f'hx01-review-{number}-{label.lower()}';attachment_ids.append(aid)
        directory=Path(var_dir)/'files/asana/review';directory.mkdir(parents=True,exist_ok=True);(directory/(aid+'.png')).write_bytes(raw)
        proposed.setdefault('attachments',[]).append(dict(attachmentId=aid,taskId=TASK,fileName=aid+'.png',fileType='image/png',fileSize=len(raw),fileUrl='/files/review/'+aid+'.png',uploaderId='user-mireya',uploadDate=now))
    text=('Final placement accepted. The WordPress reproduction line is readable and the accepted Pinterest upload is unchanged. You may close this task.' if accepted else 'Placement review: Pinterest accepted; retain this exact Pin and image. The WordPress feature viewport trims the reproduction line. Raise the reproduction credit layer to the clear upper-left tide band: X=-400 px, Y=-480 px in the WordPress layered crop, export a replacement feature image, update the existing article, and resubmit both live links. Keep the approved print layers and the accepted Pin unchanged.')
    if reviews and not unchanged:text='The accepted Pinterest version changed. Restore the first accepted Pin image before resubmitting. '+text
    if rejected=='pinterest':
        text = ('Final placement accepted. WordPress accepted asset is unchanged and Pinterest reproduction line is readable.' if accepted else 'WordPress accepted; retain this exact featured media. The Pinterest display viewport trims the reproduction line. Move the reproduction credit layer to the clear upper tide band on the portrait only: X=0, Y=-580 px. Replace the rejected Pin artwork and resubmit both links. Keep the accepted article image unchanged.')
    text+=' Reviewed WordPress media '+media['id']+'; Pinterest Pin '+pin['id']+'. See attached actual placement captures.'
    proposed.setdefault('comments',[]).append(dict(commentId=f'hx01-review-{number}',taskId=TASK,userId='user-mireya',content=text,createdDate=now,likedBy=[]))
    task=next((x for x in proposed.get('tasks',[]) if x.get('taskId')==TASK),None)
    if task:
        task['attachmentIds']=list(dict.fromkeys(task.get('attachmentIds',[])+attachment_ids))
        if not accepted:task.update(completed=False,completedDate=None)
    return proposed
