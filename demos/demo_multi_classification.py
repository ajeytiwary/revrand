#! /usr/bin/env python3
""" A La Carte GP Classification example on USPS digits dataset. """

import numpy as np
import logging

from sklearn.linear_model import LogisticRegression

from revrand.utils.datasets import fetch_gpml_usps_resampled_data
from revrand import classification, basis_functions
from revrand.validation import loglosscat, errrate


#
# Settings
#

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# A la Carte classifier setting
nbases = 1000
lenscale = 5
reg = 1e3
doSGD = False
method = 'MAP'
numdigits = 9

#
# Load data
#
usps_resampled = fetch_gpml_usps_resampled_data()

X = usps_resampled.train.data
Y = usps_resampled.train.targets

Xs = usps_resampled.test.data
Ys = usps_resampled.test.targets

# Sort and Remove excess labels (specified by numdigits)
sorted_idx = np.argsort(Y)
X = X[sorted_idx,:]
Y = Y[sorted_idx]
sorted_idx_s = np.argsort(Ys)
Xs = Xs[sorted_idx_s,:]
Ys = Ys[sorted_idx_s]
end_id= np.argwhere(Y==numdigits)[0][0]
X = X[:end_id,:]
Y = Y[:end_id]
end_id_s= np.where(Ys==numdigits)[0][0]
Xs = Xs[:end_id_s,:]
Ys = Ys[:end_id_s]


# Classify
Phi = basis_functions.RandomRBF(nbases, X.shape[1])
if method == 'SGD':
    weights, labels = classification.learn_sgd(X, Y, Phi, (lenscale,),
                                               regulariser=reg)
elif method == 'MAP':
    weights, labels = classification.learn_map(X, Y, Phi, (lenscale,),
                                               regulariser=reg)
else:
    raise ValueError("Invalid method chosen!")

lreg = LogisticRegression(penalty='l2')
lreg.fit(X, Y)


# Predict
pys_l = classification.predict(Xs, weights, Phi, (lenscale,))


print("Logistic A La Carte: av nll = {:.6f}, error rate = {:.6f}"
      .format(loglosscat(Ys, pys_l), errrate(Ys, pys_l)))

pys_r = lreg.predict_proba(Xs)
print("Logistic Scikit: av nll = {:.6f}, error rate = {:.6f}"
      .format(loglosscat(Ys, pys_r), errrate(Ys, pys_r)))