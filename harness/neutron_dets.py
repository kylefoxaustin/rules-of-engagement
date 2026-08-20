#!/usr/bin/env python3
"""Emit FINAL detections (post-NMS) from the Neutron int8 models, for comparison
against the host fp32 reference. M31: correctness is a quantitative agreement with
the reference, not 'n_det > 0'."""
import sys, json
import numpy as np
from PIL import Image
import tflite_runtime.interpreter as tflite
DEL="/usr/lib/libneutron_delegate.so"; IMG="/root/busy.jpg"

def nms(boxes, scores, thr=0.7):
    idx=np.argsort(-scores); keep=[]
    while idx.size:
        i=idx[0]; keep.append(i)
        if idx.size==1: break
        b=boxes[i]; o=boxes[idx[1:]]
        xx1=np.maximum(b[0]-b[2]/2,o[:,0]-o[:,2]/2); yy1=np.maximum(b[1]-b[3]/2,o[:,1]-o[:,3]/2)
        xx2=np.minimum(b[0]+b[2]/2,o[:,0]+o[:,2]/2); yy2=np.minimum(b[1]+b[3]/2,o[:,1]+o[:,3]/2)
        inter=np.clip(xx2-xx1,0,None)*np.clip(yy2-yy1,0,None)
        iou=inter/(b[2]*b[3]+o[:,2]*o[:,3]-inter+1e-9)
        idx=idx[1:][iou<thr]
    return keep

res={}
for name in ("yolov8n","yolov8l","yolov8s","yolov8m","yolov8x"):
    p=f"/root/{name}_eiq313.tflite"
    try:
        it=tflite.Interpreter(model_path=p,num_threads=4,
             experimental_delegates=[tflite.load_delegate(DEL)])
        it.allocate_tensors()
        ind,outd=it.get_input_details()[0],it.get_output_details()[0]
        s,z=ind["quantization"]; h,w=ind["shape"][1],ind["shape"][2]
        a=np.asarray(Image.open(IMG).convert("RGB").resize((w,h),Image.BILINEAR)).astype(np.float32)/255.0
        it.set_tensor(ind["index"], np.clip(np.round(a/(s or 1.0)+z),-128,127).astype(np.int8)[None])
        it.invoke()
        y=it.get_tensor(outd["index"]); oq=outd["quantization"]
        m=(y[0].astype(np.float32)-oq[1])*oq[0]
        if m.shape[0]>m.shape[1]: m=m.T
        box,cls=m[:4].T,m[4:]
        conf=cls.max(axis=0); lab=cls.argmax(axis=0)
        sel=conf>0.25
        keep=nms(box[sel],conf[sel]) if sel.sum() else []
        b2,c2,l2=box[sel],conf[sel],lab[sel]
        dets=[{"cls":int(l2[k]),"conf":round(float(c2[k]),4),
               "xywhn":[round(float(v),4) for v in b2[k]]} for k in keep]
        dets.sort(key=lambda d:-d["conf"])
        res[name]={"n_det":len(dets),"max_conf":dets[0]["conf"] if dets else 0.0,"dets":dets[:15]}
        print(f"{name}: {len(dets)} final dets, max {res[name]['max_conf']}", flush=True)
    except Exception as e:
        res[name]={"ERROR":str(e)[:150]}; print(f"{name}: ERROR {e}", flush=True)
json.dump(res,open("/root/neutron_final_dets.json","w"),indent=2)
