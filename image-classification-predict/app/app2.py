#!/usr/bin/python
import os
import json
import boto3
import tempfile
import urllib3

import mxnet as mx
import numpy as np
import cv2
from collections import namedtuple
from flask import Flask, Response
from flask import request
from flask import jsonify

from botocore import UNSIGNED
from botocore.config import Config

Batch = namedtuple('Batch', ['data'])

#download model files
f_params = 'resnet-18-0000.params'
f_symbol = 'resnet-18-symbol.json'

bucket = 'ecs-mxnet-example'
s3 = boto3.resource('s3')
s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))

#params
f_params_file = tempfile.NamedTemporaryFile()
s3_client.download_file(bucket, f_params, f_params_file.name)
f_params_file.flush()

#symbol
f_symbol_file = tempfile.NamedTemporaryFile()
s3_client.download_file(bucket, f_symbol, f_symbol_file.name)
f_symbol_file.flush()

print (f_symbol_file.name)

def load_model(s_fname, p_fname):
     """
     Load model checkpoint from file.
     :return: (arg_params, aux_params)
     arg_params : dict of str to NDArray
         Model parameter, dict of name to NDArray of net's weights.
     aux_params : dict of str to NDArray
         Model parameter, dict of name to NDArray of net's auxiliary states.
     """
     symbol = mx.symbol.load(s_fname)
     save_dict = mx.nd.load(p_fname)
     arg_params = {}
     aux_params = {}
     for k, v in save_dict.items():
         tp, name = k.split(':', 1)
         if tp == 'arg':
             arg_params[name] = v
         if tp == 'aux':
             aux_params[name] = v
     return symbol, arg_params, aux_params

def predict(url, mod, synsets):
     req = urllib3.urlopen(url)
     arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
     cv2_img = cv2.imdecode(arr, -1)
     img = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
     if img is None:
         return None
     img = cv2.resize(img, (224, 224))
     img = np.swapaxes(img, 0, 2)
     img = np.swapaxes(img, 1, 2)
     img = img[np.newaxis, :]

     mod.forward(Batch([mx.nd.array(img)]))
     prob = mod.get_outputs()[0].asnumpy()
     prob = np.squeeze(prob)

     a = np.argsort(prob)[::-1]
     out = ''
     for i in a[0:5]:
         out += 'probability=%f, class=%s' %(prob[i], synsets[i])
     out += "\n"
     return out

with open('/app/synset.txt', 'r') as f:
     synsets = [l.rstrip() for l in f]

app = Flask(__name__)

@app.route('/')
def index():
    resp = Response(response="Success",
         status=200, \
         mimetype="application/json")
    return (resp)

@app.route('/image')
def image():
    print('api')
    url = request.args.get('image')
    print(url)


    sym, arg_params, aux_params = load_model(f_symbol_file.name, f_params_file.name)
    mod = mx.mod.Module(symbol=sym, context=mx.cpu())
    mod.bind(for_training=False, data_shapes=[('data', (1,3,224,224))])
    mod.set_params(arg_params, aux_params)

    labels = predict(url, mod, synsets)

    resp = Response(response=labels,
    status=200, \
    mimetype="application/json")

    return(resp)

if __name__ == '__main__':
    app.run('0.0.0.0', debug=True)
