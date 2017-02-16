# Copyright (c) Microsoft. All rights reserved.

# Licensed under the MIT license. See LICENSE.md file in the project root
# for full license information.
# ==============================================================================

import numpy as np
from cntk import *

# Note: We do not test gradients here, assuming that those are tested elsewhere.
# Forward outputs are tested to verify that the structure of the layer is as expected.

def test_layers_name(device_id):
    from cntk import placeholder_variable
    I = placeholder_variable(name='input')
    p = Dense(10, name='dense10')(I)
    assert(I.name == 'input')
    assert(p.root_function.name == 'dense10')
    
    q = Convolution((3, 3), 3, name='conv33')(I)
    assert(q.root_function.name == 'conv33')

    e = Embedding(0, name='emb')(I)
    assert(e.root_function.name == 'emb')

    e = Embedding(0, name='')(I)
    assert(e.root_function.name == '')
    
def _getModelParameterDict(model, node_name):
    node_dict = {}
    for attr in getattr(model, node_name).parameters:
        node_dict[attr.name] = np.matrix(attr.value) 
    return node_dict

####################################
# Recurrence()
# Note: Run this first, since it uses random init; result will change if moved down.
# TODO: How to reset the RNG?
####################################    

def test_recurrence():
    r = Recurrence(GRU(5), go_backwards=False)
    a = input_variable(shape=(5,), dynamic_axes=[Axis.default_batch_axis(), Axis('Seq')])
    x = np.reshape(np.arange(0,25, dtype=np.float32), (1,5,5))
    rt = r(a).eval({a:x})
    exp = [[ 0.403719,  0.138464, -0.41292 , -0.527761, -0.552515],
           [ 0.432029, -0.967444, -0.498568, -0.973288, -0.98996 ],
           [-0.193994, -0.999806, -0.527336, -0.999831, -0.999987],
           [-0.875168, -0.999995, -0.532773, -1.      , -1.      ],
           [-0.989135, -1.      , -0.533798, -1.      , -1.      ]]
    np.testing.assert_array_almost_equal(rt[0], exp, decimal=6, err_msg='Error in Recurrence(GRU()) forward')

####################################
# Recurrence() over regular function
####################################    

def test_recurrence_fun(device_id):
    from cntk.layers import Recurrence
    from cntk.ops import plus

    ####################################################
    # Test 1: sum-reduction over sequence
    ####################################################
    r = Fold(plus)
    r.update_signature(1)
    data = [np.array([[2], [6], [4], [8], [6]])]   # simple sequence
    out = r(data)
    exp = [[sum(data[0])]]
    np.testing.assert_array_equal(out, exp, err_msg='Error in recurrence over plus')

    ####################################################
    # Test 2: max-pool over sequence
    ####################################################
    r = Fold(element_max)
    r.update_signature(2)
    data = [np.array([[2,1], [6,3], [4,2], [8,1], [6,0]])]   # simple sequence
    out = r(data)
    exp = [[np.max(data[0], axis=0)]]
    np.testing.assert_array_equal(out, exp, err_msg='Error in recurrence over element_max')

####################################
# Test dense layer for correctness
####################################    

def test_layers_dense(device_id):
    y = Input(2)
    dat = np.array([[-1., 1.]], dtype=np.float32)
    
    ####################################################
    # Test 1: no activation
    ####################################################
    p = Dense(2, activation=None, name='foo')(y)
    res = p(y).eval({y: dat})
    
    # Get the network paramters
    fooDict = _getModelParameterDict(p, 'foo')
    
    npout = np.matrix(dat[0]) * fooDict['W'] + fooDict['b']
    print(res[0])
    print(npout)
    np.testing.assert_array_equal(res[0], npout, err_msg='Error in dense layer')
    
    ####################################################
    # Test 2: with activation
    ####################################################
    p = Dense(2, activation=sigmoid, name='foo')(y)
    res = p(y).eval({y: dat})
    
    # Get the network paramters
    fooDict = _getModelParameterDict(p, 'foo')
    
    def _sigmoid(x): 
        return 1./(1 + np.exp(-x))
    
    npout = _sigmoid(np.matrix(dat[0]) * fooDict['W'] + fooDict['b'])
    print(res[0])
    print(npout)
    
    np.testing.assert_array_almost_equal(res[0], npout, decimal=7, err_msg='Error in dense layer with sigmoid')
    
    ####################################################
    # Test 3: 2-dense layer
    ####################################################
    p = Dense(3, activation=None, name='foo')(y)
    q = Dense(3, activation=None, name='bar')(p)
    res = q(y).eval({y: dat})
    
    # Get the network paramters for the two layers        
    fooDict = _getModelParameterDict(q, 'foo')
    barDict = _getModelParameterDict(q, 'bar')  
    
    npout1 = np.matrix(dat[0]) * fooDict['W'] + fooDict['b']
    npout = npout1 * barDict['W'] + barDict['b']
            
    np.testing.assert_array_almost_equal(res[0], npout, decimal=7, err_msg='Error in 2-dense layer')

########################################
# Test Embedding layer for correctness
########################################    
def test_layers_embedding(device_id):
    embDim = 3
    
    y = Input(2)
    e = Embedding(shape=embDim, name='foo')
    
    dat = np.array([[-1., 1.]], dtype=np.float32)
    res = e(y).eval({y: dat})
    
    npout = np.matrix(dat[0]) * e.foo.parameters[0].value
    np.testing.assert_array_equal(res[0], npout, err_msg='Error in embedding layer')

########################################
# Test Convolutional layer for shape correctness
########################################   

def _getConvOutShape(inDim, kernelDim, zeroPad, strides):
    # First we tackle unit stride
    i, k, s = inDim, kernelDim, strides
    
    if zeroPad == False:
        if s == 1:
            return inDim - kernelDim + 1
        elif s > 1:
            return int(np.floor((i - k)/s) + 1)
        else:
            raise ValueError("Stride must be a non-zero positive number")
    else: #Zero padding == True
        if s == 1:
            return i 
        elif s > 1:
            p = k//2
            return int(np.floor((i + 2 * p -k)/s) + 1)
        else:
            raise ValueError("Stride must be a non-zero positive number")
    
def test_layers_convolution_shape(device_id):
    # Get the output shape
    # i: input dimension
    # k: kernel dimension
    # p: number of zero padding
    # s: strides
    inC, inH, inW = 2, 6, 7
    y = Input((inC, inH, inW))
    in_rf_shape = (3, 2)
    out_num_filters = 4

    ##########################################################
    # Test convolutional layer for correctness (p=False s = 1)
    ##########################################################
    zeropad = False
    in_strides = 1
    
    model = Convolution(rf_shape=in_rf_shape, 
                                 num_filters=out_num_filters,
                                 activation=None,
                                 pad=zeropad,
                                 strides=in_strides, name='foo')    
    # shape should be 
    model_shape = model(y).foo.shape
                
    expected_shape = (out_num_filters, 
                      _getConvOutShape(inH, in_rf_shape[0], zeropad, in_strides),
                      _getConvOutShape(inW, in_rf_shape[1], zeropad, in_strides))

    np.testing.assert_array_equal(model_shape, expected_shape, \
        "Error in convolution with stride = 1 with no padding")
    
    ############################################################
    # Test convolutional layer for correctness (p=True s = (3,2))
    ############################################################
    zeropad = False
    in_strides_t = (2, 3)
    
    model = Convolution(rf_shape=in_rf_shape, 
                                 num_filters=out_num_filters,
                                 activation=None,
                                 pad=zeropad,
                                 strides=in_strides_t, name='foo')
    # shape should be 
    model_shape = model(y).foo.shape
                
    expected_shape = (out_num_filters, 
                      _getConvOutShape(inH, in_rf_shape[0], zeropad, in_strides_t[0]),
                      _getConvOutShape(inW, in_rf_shape[1], zeropad, in_strides_t[1]))

    np.testing.assert_array_equal(model_shape, expected_shape, \
        "Error in convolution with stride>1 with no padding")
    
    ##########################################################
    # Test convolutional layer for correctness (pad=True s = 1)
    ##########################################################
    zeropad = True
    in_strides = 1
    
    model = Convolution(rf_shape=in_rf_shape, 
                                 num_filters=out_num_filters,
                                 activation=None,
                                 pad=zeropad,
                                 strides=in_strides, name='foo')
    # shape should be 
    model_shape = model(y).foo.shape  
                       
    expected_shape = (out_num_filters, 
                      _getConvOutShape(inH, in_rf_shape[0], zeropad, in_strides),
                      _getConvOutShape(inW, in_rf_shape[1], zeropad, in_strides))
    print(expected_shape) 
    np.testing.assert_array_equal(model_shape, expected_shape, \
        "Error in convolution with stride = 1 and padding")
    
    ##########################################################
    # Test convolutional layer for correctness (pad=True s = 2)
    ##########################################################
    zeropad = True
    in_strides = 2
    
    model = Convolution(rf_shape=in_rf_shape, 
                                 num_filters=out_num_filters,
                                 activation=None,
                                 pad=zeropad,
                                 strides=in_strides, name='foo')
    
    # shape should be 
    model_shape = model(y).foo.shape
                  
    expected_shape = (out_num_filters, 
                      _getConvOutShape(inH, in_rf_shape[0], zeropad, in_strides),
                      _getConvOutShape(inW, in_rf_shape[1], zeropad, in_strides))

    np.testing.assert_array_equal(model_shape, expected_shape, \
        "Error in convolution with stride > 1 and padding")

def  test_layers_convolution_value(device_id):
    
    # Common parameters
    inC, inH, inW = 1, 3, 3   
    in_rf_shape = (3, 3)
    out_num_filters = 1
    dat = np.ones([1, inC, inH, inW], dtype = np.float32)
    
    ##########################################################
    # Test convolutional layer for correctness (p=False s = 1)
    ##########################################################    
    y = Input((inC, inH, inW))
    zeropad = False
    in_strides = 1

    model = Convolution(rf_shape=in_rf_shape, 
                                 num_filters=out_num_filters,
                                 activation=None,
                                 pad=zeropad,
                                 strides=in_strides, name='foo')        
    res = model(y).eval({y: dat})
    
    # Extract the W weight matrix
    expected_res = np.sum(getattr(model, 'foo').parameters[0].value)
    
    np.testing.assert_array_almost_equal(res[0][0][0][0][0], expected_res, decimal=7, \
        err_msg="Error in convolution computation with stride = 1 and zeropad = False")
    
    ##########################################################
    # Test convolutional layer for correctness (p=False s = 2)
    ##########################################################
    zeropad = False
    in_strides = 2
    
    model = Convolution(rf_shape=in_rf_shape, 
                                 num_filters=out_num_filters,
                                 activation=None,
                                 pad=zeropad,
                                 strides=in_strides, name='foo')          
    res = model(y).eval({y: dat})
    
    # Extract the W weight matrix
    expected_res = np.sum(getattr(model, 'foo').parameters[0].value)
    
    np.testing.assert_array_almost_equal(res[0][0][0][0][0], expected_res, decimal=7, \
        err_msg="Error in convolution computation with stride = 2 and zeropad = False")
    
    ##########################################################
    # Test convolutional layer for correctness (p=True s = 1)
    ##########################################################
    zeropad = True
    in_strides = 1    
    
    model = Convolution(rf_shape=in_rf_shape, 
                                 num_filters=out_num_filters,
                                 activation=None,
                                 pad=zeropad,
                                 strides=in_strides, name='foo')            
    res = model(y).eval({y: dat})
    
    # Extract the W weight matrix
    expected_res = np.sum(getattr(model, 'foo').parameters[0].value)
    
    # Compare the center of the res with the sum of the weights
    np.testing.assert_array_almost_equal(res[0][0][0][1][1], expected_res, decimal=7, \
        err_msg="Error in convolution computation with stride = 1 and zeropad = True")
    
    ##########################################################
    # Test convolutional layer for correctness (p=True s = 1)
    ##########################################################
    zeropad = True
    in_strides = 2
    
    model = Convolution(rf_shape=in_rf_shape, 
                                 num_filters=out_num_filters,
                                 activation=None,
                                 pad=zeropad,
                                 strides=in_strides, name='foo')              
    res = model(y).eval({y: dat})
    
    # Extract the W weight matrix
    W = getattr(model, 'foo').parameters[0].value
    expected_res = np.sum(W[0][0][1:,1:])
    
    # Compare the center of the res with the sum of the weights
    np.testing.assert_array_almost_equal(res[0][0][0][0][0], expected_res, decimal=5,
        err_msg="Error in convolution computation with stride = 1 and zeropad = True")    

##########################################################
# Test convolutional 3D layer for correctness (p=False s = 1)
##########################################################
def  test_layers_convolution_3d(device_id):
    inC, inH, inW, inD = 1, 3, 3, 3
    y = Input((inC,inH, inW, inD))    
    dat = np.ones([1, inC, inH, inW, inD], dtype = np.float32)
    
    model = Convolution3D(rf_shape=(3, 3, 3), 
                                 num_filters=1,
                                 activation=None,
                                 pad=False,
                                 strides=1, name='foo')
    # shape should be 
    model_shape = model(y).foo.shape
 
    np.testing.assert_array_equal(model_shape, (1, 1, 1, 1), \
        "Error in convolution3D with stride = 1 and padding")
                 
    res = model(y).eval({y: dat})
    
    expected_res = np.sum(getattr(model, 'foo').parameters[0].value)
    
    np.testing.assert_array_almost_equal(res[0][0][0][0][0][0], expected_res, decimal=5, \
        err_msg="Error in convolution3D computation with stride = 1 and zeropad = True")  
    
##########################################################
# Test convolutional 2D layer for correctness (p=False s = 1)
##########################################################
def test_layers_convolution_2d(device_id):
    inC, inH, inW = 1, 3, 3
    y = Input((inC,inH, inW))
    
    dat = np.ones([1, inC, inH, inW], dtype = np.float32)
    
    model = Convolution2D(rf_shape=(3, 3), 
                                 num_filters=1,
                                 activation=None,
                                 pad=False,
                                 strides=1, name='foo')
    # shape should be 
    model_shape = model(y).foo.shape
    np.testing.assert_array_equal(model_shape, (1, 1, 1), \
        "Error in convolution2D with stride = 1 and padding")
                 
    res = model(y).eval({y: dat})
    
    expected_res = np.sum(getattr(model, 'foo').parameters[0].value)
    
    np.testing.assert_array_almost_equal(res[0][0][0][0][0], expected_res, decimal=5, \
        err_msg="Error in convolution2D computation with stride = 1 and zeropad = True")    
    
####################################
# sequential convolution without reduction dimension
####################################

def test_sequential_convolution_without_reduction_dim(device_id):
    c = Convolution(3, init=np.array([4, 2, 1]), sequential=True, pad=False, reduction_rank=0, bias=False)
    c.update_signature(1)
    data = [np.array([[2], [6], [4], [8], [6]])]   # like a short audio sequence, in the dynamic dimension
    out = c(data)
    exp = [[[24], [40], [38]]]
    np.testing.assert_array_equal(out, exp, err_msg='Error in sequential convolution without reduction dimension')

####################################
# 1D convolution without reduction dimension
####################################

def test_1D_convolution_without_reduction_dim(device_id):
    c = Convolution1D(3, init=np.array([4, 2, 1]), pad=True, reduction_rank=0, bias=False)
    ## BUGBUG: pad seems ignored??
    c.update_signature(5)
    data = [np.array([[2, 6, 4, 8, 6]])]   # like a audio sequence, in a static dimension
    out = c(data)
    exp = [[[24, 40, 38]]]
    np.testing.assert_array_equal(out, exp, err_msg='Error in 1D convolution without reduction dimension')

##########################################################
# Test Deconvolution layer for correctness 
##########################################################
# TESTTODO: Add the test for deconvolution once current bug with lower/upper pad is fixed
def test_layers_deconvolution(device_id):
    pass

##########################################################
# Test Conv/Pooling/Unpooling/Deconvolution and layer for correctness 
##########################################################
# TESTTODO: Add the test for deconvolution once current bug with lower/upper pad is fixed
def test_layers_conv_pool_unpool_deconv(device_id):
    pass
#    inC, inH, inW = 1,4,4
#    
#    y = Input((inC,inH, inW))
#    
#    cMap =1
#    
#    
#    conv = Convolution((2,2), cMap, pad=True, activation=None, name='foo' )(y)
#    
#    pool = MaxPooling((2,2), (2,2), name='bar')(conv)
#    
#    unpool = MaxUnpooling ((4,4), (4,4), name ='baz')(pool, conv)
#    
#    z = Deconvolution((2,2), inC, cMap, 
#                                  lower_pad=(0,2,2), 
#                                  upper_pad=(0,2,2), 
#                                  bias=False, 
#                                  init=glorot_uniform(0.001))(unpool,
#                                  name='faz')
#    
#    
#    print(z.faz.shape)
#    
#    dat = np.arange(0,16, dtype=np.float32).reshape(1,1,4,4)
#    maxpool   = MaxPooling   (rf_shape=(2,2), strides=(2,2), name='bar')
#    print(maxpool(y).shape)
#    
#    
#    res = maxpool(y).eval({y: dat})
#    print(res)
#    
#    maxunpool = MaxUnpooling(filter_shape=(2,2), 
#                                      strides=(2,2), 
#                                      name='foo')((maxpool),(y))
#    
#    # Add a few asserts (1 for value and other for shape once this is running)

##########################################################
# Test for dropout
##########################################################
def test_layers_dropout(device_id):
    dat = np.array([[1., 1., 1., 1.]], dtype=np.float32)  
    y = Input(4)  
    p = Dense(1, activation=None, name='foo')(y)                 
    z = Dropout(prob=0.75, name='bar')(p)
    
    # Get the network paramters
    fooDict = {}
    for attr in getattr(p, 'foo').parameters:
        fooDict[attr.name] = np.matrix(attr.value)
    
    res =  z(y).eval({y: dat}) 
    expected_res = np.sum(fooDict['W'])
    
    np.testing.assert_array_almost_equal(res, expected_res, decimal=7, \
        err_msg="Error in dropout computation")
    
##########################################################
# Test for LayerNormalization
##########################################################    
def test_layers_layer_normalization(device_id):
    y = Input(4) 
    p = LayerNormalization(name='foo')(y)                 
    
    dat = np.array([[1.0,2.0,3.0,4.0]], dtype=np.float32)
    res =  p(y).eval({y: dat}) 
    
    mean_dat = np.mean(dat) 
    x = dat-mean_dat
    std = np.sqrt(np.mean(x*x))
    epsilon = 0.00001

    np.testing.assert_array_almost_equal(res[0], x/(std + epsilon), decimal=6, \
        err_msg="Error in layer normalization computation") 
    
##########################################################
# Test for BatchNormalization
##########################################################   
# TESTTODO: Currently the result doesn't match the expected result 
def test_layers_batch_normalization(device_id):
    pass
#    dat = np.array([[1.0,0.5,1.0,0.5]], dtype=np.float32)    
#    y = Input(4) 
#    p = BatchNormalization(init_scale=2
#                                     normalization_time_constant=0,
#                                     name ='foo')(y)                 
#
#    res =  p(y).eval({y: dat}) 
#    
#    mean_dat = np.mean(dat) 
#    x = dat-mean_dat
#    std = np.sqrt(np.mean(x*x))       
#    bias = 0
#    scale = 2
#    expected_res = scale * (x/(std + 0.00001)) + bias
#    np.testing.assert_array_almost_equal(res[0], expected_res, decimal=5, \
#         err_msg="Error in BN computation") 
