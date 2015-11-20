"""
Implementation of Bayesian GLMs with nonparametric variational inference [1_],
with a few modifications and tweaks.

.. [1] Gershman, S., Hoffman, M., & Blei, D. "Nonparametric variational
       inference". arXiv preprint arXiv:1206.4665 (2012).
"""


from __future__ import division

import numpy as np
import logging
from scipy.stats.distributions import gamma

from .transforms import logsumexp
from .optimize import minimize, sgd
from .utils import CatParameters, Bound, Positive, checktypes

# Set up logging
log = logging.getLogger(__name__)


def glm_learn(y, X, likelihood, lparams, basis, bparams, reg=1., postcomp=10,
              use_sgd=False, maxit=1000, tol=1e-7, batchsize=100, rate=0.9,
              eta=1e-5, verbose=True):

    N, d = X.shape
    D = basis(np.atleast_2d(X[0, :]), *bparams).shape[1]
    K = postcomp

    # Objective function Eq. 10 from [1], and gradients of ALL params
    def L2(params, data):

        # Extract data, parameters, etc
        y, X = data[:, 0], data[:, 1:]
        uparams = pcat.unflatten(params)
        _m, _C, _reg, _lparams, _bparams = uparams

        # Dimensions
        M, d = X.shape
        D, K = _m.shape
        B = N / M

        # Basis function stuff
        Phi = basis(X, *_bparams)  # N x D
        Phi2 = Phi**2
        # dPhi = basis.grad(X, *_bparams)
        # dPhiPhi = [dP * Phi for dP in dPhi]
        # NOTE: SLOWSLOWSLOW
        PPP = np.einsum('ij...,i...->ij...', Phi, Phi) * Phi[:, :, np.newaxis]
        f = Phi.dot(_m)  # N x K

        # Posterior responsability terms
        logqkk = qmatrix(_m, _C)
        logqk = logsumexp(logqkk, axis=1)  # log term of Eq. 7 from [1]
        pz = np.exp(logqkk - logqk)

        # Big loop though posterior mixtures for calculating stuff
        ll = 0
        dm = np.empty_like(_m)
        dC = np.empty_like(_C)
        H = np.empty_like(_C)
        dlp = [np.zeros_like(p) for p in _lparams]
        dbp = [np.zeros_like(p) for p in _bparams]

        for k in range(K):

            # Common likelihood calculations
            ll += B * likelihood.loglike(y, f[:, k], *_lparams).sum()
            df = B * likelihood.df(y, f[:, k], *_lparams)
            d2f = B * likelihood.d2f(y, f[:, k], *_lparams)
            d3f = B * likelihood.d3f(y, f[:, k], *_lparams)
            H[:, k] = d2f.dot(Phi2) - 1. / _reg

            # Posterior mean and covariance gradients
            mkmj = _m[:, k:k + 1] - _m
            iCkCj = 1 / (_C[:, k:k + 1] + _C)
            # dC[:, k] = (H[:, k] - (mkmj**2 * iCkCj**2 - iCkCj).dot(pz[k])) \
            #     / (2 * K)
            PPPL = (PPP * d3f[:, np.newaxis, np.newaxis]).sum(axis=0)\
                .sum(axis=0)  # NOTE: SLOW SLOW SLOW!!
            dm[:, k] = (df.dot(Phi) + 0.5 * _C[:, k] * PPPL
                        - 2 * (pz[k] * iCkCj * mkmj).sum(axis=1)
                        - _m[:, k] / _reg) / K

            # Likelihood parameter gradients
            # dp = likelihood.dp(y, f[:, k], *_lparams)
            # dp2df = likelihood.dpd2f(y, f[:, k], *_lparams)
            # for l in range(len(_lparams)):
            #     dpH = dp2df[l].dot(Phi2)
            #     dlp[l] += B * (dp[l].sum() + 0.5 * (_C[:, k] * dpH).sum()) / K

            # Basis function parameter gradients
            # for l in range(len(_bparams)):
            #     dPhiH = d2f.dot(dPhiPhi[l]) \
            #         + 0.5 * (d3f * dPhi[l].dot(_m[:, k])).dot(Phi2)
            #     dbp[l] += (df.dot(dPhi[l].dot(_m[:, k]))
            #                + (_C[:, k] * dPhiH).sum()) / K

        # Regulariser gradient
        dreg = (((_m**2).sum() + _C.sum()) / (_reg * K) - D) / (2 * _reg)
        # dreg = 0.0

        # Objective, Eq. 10 in [1]
        L2 = 1. / K * (np.sum(ll)
                       - 0.5 * D * K * np.log(2 * np.pi * _reg)
                       - 0.5 * (_m**2).sum() / _reg
                       + 0.5 * (_C * H).sum()
                       - logqk.sum()) + np.log(K)

        if verbose:
            log.info("L2 = {}, reg = {}, lparams = {}, bparams = {}"
                     .format(L2, _reg, _lparams, _bparams))

        # print('dreg = ', dreg, 'dm = ', np.linalg.norm(dm.flatten()),
        #       'dC = ', np.linalg.norm(dC.flatten()))

        return -L2, -pcat.flatten_grads(uparams, [dm, dC, dreg, dlp, dbp])

    # Intialise m and C
    m = np.random.randn(D, K)
    # C = gamma.rvs(2, scale=0.5, size=(D, K))
    C = gamma.rvs(1, scale=0.1, size=(D, K))

    # Optimiser boiler plate for bounds, log trick, etc
    # NOTE: It would be nice if the optimizer knew how to handle Positive
    # bounds when the log trick is used, so we dont have to have this boiler
    # plate...
    bounds = [Bound()] * (2 * np.prod(m.shape) + 1)
    loginds = [1, 2]
    if checktypes(likelihood.bounds, Positive):
        loginds.append(3)
        bounds += [Bound()] * len(likelihood.bounds)
    else:
        bounds += likelihood.bounds
    if checktypes(basis.bounds, Positive):
        loginds.append(4)
        bounds += [Bound()] * len(basis.bounds)
    else:
        bounds += basis.bounds
    pcat = CatParameters([m, C, reg, lparams, bparams], log_indices=loginds)

    if use_sgd is False:
        # res = minimize(L2, pcat.flatten([m, C, reg, lparams, bparams]),
        #                ftol=tol, maxeval=maxit, method=None,
        #                bounds=bounds, args=(np.hstack((y[:, np.newaxis], X)),),
        #                jac=False, xtol=1e-8)
        res = minimize(L2, pcat.flatten([m, C, reg, lparams, bparams]),
                       ftol=tol, maxiter=maxit, method='L-BFGS-B', jac=True,
                       bounds=bounds, args=(np.hstack((y[:, np.newaxis], X)),))
    else:
        res = sgd(L2, pcat.flatten([m, C, reg, lparams, bparams]),
                  np.hstack((y[:, np.newaxis], X)), rate=rate, eta=eta,
                  bounds=bounds, gtol=tol, passes=maxit, batchsize=batchsize,
                  eval_obj=True)
        import matplotlib.pyplot as pl
        pl.plot(range(len(res.objs)), res.objs, 'b', range(len(res.norms)),
                res.norms, 'r')
        pl.show()
        m, C, reg, lparams, bparams = pcat.unflatten(res.x)

    if verbose:
        log.info("Finished! Objective = {}, reg = {}, lparams = {}, "
                 "bparams = {}, message: {}."
                 .format(-res.fun, reg, lparams, bparams, res.message))

    return m, C, lparams, bparams


def glm_predict(Xs, likelihood, basis, m, C, lparams, bparams,
                nsamples=100):

    D, K = m.shape
    w = np.zeros((D, nsamples))

    for k in range(K):
        w += m[:, k:k + 1] + np.random.randn(D, nsamples) \
            * np.sqrt(C[:, k:k + 1])

    w /= K
    f = basis(Xs, *bparams).dot(w)

    return likelihood.Ey(f, *lparams)  # .mean(axis=1)


#
# Private module functions
#

def dgausll(x, mean, dcov):

    D = len(x)
    return - 0.5 * (D * np.log(2 * np.pi) + np.log(dcov).sum()
                    + ((x - mean)**2 / dcov).sum())


def qmatrix(m, C, k=None):

    K = m.shape[1]
    if k is None:
        logq = [[dgausll(m[:, i], m[:, j], C[:, i] + C[:, j])
                 for i in range(K)]
                for j in range(K)]
    else:
        logq = [dgausll(m[:, k], m[:, j], C[:, k] + C[:, j]) for j in range(K)]

    return np.array(logq)
