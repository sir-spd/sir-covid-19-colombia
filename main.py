import os
import json
import requests

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy import optimize
from scipy.integrate import odeint

if not os.path.exists("data"):
    os.makedirs("data")

if not os.path.exists("images"):
    os.makedirs("images")

# download file

url = "https://e.infogram.com/api/live/flex/4524241a-91a7-4bbd-a58e-63c12fb2952f/fe40de25-f64d-445f-a026-224e4ca25999"
s = requests.get(url).text

# read file

columns = json.loads(s)["data"][0][0]
data = json.loads(s)["data"][0][1:]
dft = pd.DataFrame(data, columns=columns)

dft.to_csv(os.path.join("data", "original-data.csv"), index=None)

# prepare
dft.columns = ["date", "dead", "cases", "recovered"]
dates = pd.date_range(pd.to_datetime(dft.loc[0,"date"], format="%d/%m/%Y"), periods=len(dft), freq="D")
dft["date"] = dates # pd.to_datetime(dft["date"], format="%d/%m/%Y")
dft = dft.set_index("date")
dft = dft.replace("",0).astype(np.float)

dfto = dft.copy()

dfpct = 100*dft["dead"]/dft["cases"]
dft["recovered"] = dft["recovered"] + dft["dead"] # as SIR model defines
dft["infected"] = dft["cases"] - dft["recovered"]

# optimization SIR

inf0 = dft["infected"].values[0]
rec0 = dft["recovered"].values[0]
days = len(dft)

def sir(N, beta, gamma, days):
    I0 = inf0
    R0 = rec0
    S0 = N - I0 - R0

    def deriv(y, t, N, beta, gamma):
        S, I, R = y
        dSdt = -beta * S * I / N
        dIdt = beta * S * I / N - gamma * I
        dRdt = gamma * I
        return dSdt, dIdt, dRdt
    
    t = np.linspace(0, days, days)
    y0 = S0, I0, R0
    ret = odeint(deriv, y0, t, args=(N, beta, gamma))
    S, I, R = ret.T

    return S, I, R

def sir_lockdown(N, beta, gamma, days, delta, lckday1, lckday2):
    I0 = inf0
    R0 = rec0
    S0 = N - I0 - R0

    def deriv(y, t, N, beta, gamma, delta):
        S, I, R = y
        dSdt = -beta * delta * S * I / N
        dIdt = beta * delta * S * I / N - gamma * I
        dRdt = gamma * I
        return dSdt, dIdt, dRdt
    
    t = np.linspace(0, days, days)

    y0 = S0, I0, R0
    t0 = t[:min(lckday1+1, days)]
    ret = odeint(deriv, y0, t0, args=(N, beta, gamma, 1))
    S, I, R = ret.T

    if lckday1 < days:
        y1 = S[-1], I[-1], R[-1]
        t1 = t[lckday1:min(lckday2+1, days)]
        ret = odeint(deriv, y1, t1, args=(N, beta, gamma, delta))
        S1, I1, R1 = ret.T
        S, I, R = np.concatenate((S, S1[1:])), np.concatenate((I, I1[1:])), np.concatenate((R, R1[1:]))

    if lckday2 < days:
        y2 = S1[-1], I1[-1], R1[-1]
        t2 = t[lckday2:]
        ret = odeint(deriv, y2, t2, args=(N, beta, gamma, 1))
        S2, I2, R2 = ret.T
        S, I, R = np.concatenate((S, S2[1:])), np.concatenate((I, I2[1:])), np.concatenate((R, R2[1:]))

    return S, I, R

def fdelay(delay):
    def f(x):
        N = x[0]
        beta = x[1]
        gamma = x[2]
        days = len(dft)
        S, I, R = sir(N, beta, gamma, days + delay)
        S, I, R = S[delay:delay+days], I[delay:delay+days], R[delay:delay+days]
        Io, Ro = dft["infected"].values, dft["recovered"].values
        #So = N - Io
        #loss = ((S - So)**2).sum()/days + ((I - Io)**2).sum()/days + ((R - Ro)**2).sum()/days
        loss = ((I - Io)**2).sum()/days + ((R - Ro)**2).sum()/days
        return loss

    result = optimize.minimize(f, [100000, 0.5, 0.05], method="Nelder-Mead")

    return result

def fdelay_lockdown(delay, lckday, nlckdays):
    def f(x):
        N = x[0]
        beta = x[1]
        gamma = x[2]
        delta = x[3]
        days = len(dft)
        S, I, R = sir_lockdown(N, beta, gamma, days + delay, delta, lckday + delay, lckday + nlckdays + delay)
        S, I, R = S[delay:delay+days], I[delay:delay+days], R[delay:delay+days]
        Io, Ro = dft["infected"].values, dft["recovered"].values
        So = N - Io - Ro
        loss = ((S - So)**2).sum()/days + ((I - Io)**2).sum()/days + ((R - Ro)**2).sum()/days
        #loss = ((I - Io)**2).sum()/days + ((R - Ro)**2).sum()/days
        return loss

    result = optimize.minimize(f, [100000, 0.5, 0.05, 0.5], method="Nelder-Mead")

    return result

lckday = dft.index.get_loc(pd.to_datetime("2020-03-25"))
nlckdays = 32 # days

delay = 0 # days back
result = fdelay_lockdown(delay, lckday, nlckdays)
for d in range(10):
    #res = fdelay(d)
    res = fdelay_lockdown(d, lckday, nlckdays)
    print("delay: {}, fun: {}".format(d, res.fun))
    if res.fun < result.fun:
        delay = d
        result = res

N = result.x[0]
beta = result.x[1]
gamma = result.x[2]
delta = result.x[3]

print("optimal: N = {}, beta = {}, gamma = {}, delta = {}, delay = {}".format(N, beta, gamma, delta, delay))
print("error: {}".format(result.fun))

#S, I, R = sir(N, beta, gamma, days + delay)
S, I, R = sir_lockdown(N, beta, gamma, days + delay, delta, lckday + delay, lckday + nlckdays + delay)
S, I, R = S[delay:delay+days], I[delay:delay+days], R[delay:delay+days]

dft["S"] = S
dft["I"] = I
dft["R"] = R

dft["susceptible"] = N - dft["infected"] - dft["recovered"]

# forecasting

far = 60 # days

#S, I, R =  sir(N, beta, gamma, days + far + delay)
S, I, R = sir_lockdown(N, beta, gamma, days + far + delay, delta, lckday + delay, lckday + nlckdays + delay)
S, I, R = S[delay:delay+days+far], I[delay:delay+days+far], R[delay:delay+days+far]
d = {
    "S": S,
    "I": I,
    "R": R,
    "susceptible": list(dft["susceptible"].values) + [np.nan]*far,
    "infected": list(dft["infected"].values) + [np.nan]*far,
    "recovered": list(dft["recovered"].values) + [np.nan]*far,
}
dff = pd.DataFrame(d)
dff["date"] = pd.date_range(dft.index[0],periods=days+far,freq="D")
dff = dff.set_index("date")

dff["cases"] = dff["recovered"] + dff["infected"]
dff["forecast"] = dff["R"] + dff["I"]
dff[["forecast", "cases"]].to_csv(os.path.join("data", "generated-cases.csv"))

# graph

metadata = {'Creator': None, 'Producer': None, 'CreationDate': None}

fig, ax = plt.subplots(figsize=(8,6))
dfto[["cases", "dead", "recovered"]].plot(ax=ax)
ax.set_title("Totals in Colombia")
ax.set_xlabel("")
ax.set_ylabel("# of occurences")
ax.grid(True, which="both")
dfto[["cases", "dead", "recovered"]].to_csv(os.path.join("data", "generated-total.csv"))
plt.savefig(os.path.join("images", "generated-total.png"), format="png", dpi=300)
plt.savefig(os.path.join("images", "generated-total.pdf"), format="pdf", dpi=300, metadata=metadata)

fig, ax = plt.subplots(figsize=(8,6))
dfpct.plot(ax=ax)
ax.set_title("Percentage of dead")
ax.set_xlabel("")
ax.set_ylabel("%")
ax.grid(True, which="both")
plt.savefig(os.path.join("images", "generated-deadpct.png"), format="png", dpi=300)
plt.savefig(os.path.join("images", "generated-deadpct.pdf"), format="pdf", dpi=300, metadata=metadata)

fig, ax = plt.subplots(figsize=(8,6))
dff[["susceptible"]].plot(ax=ax, alpha=0.5)
dff[["infected", "recovered"]].plot(ax=ax)
dff[["S", "I", "R"]].plot(ax=ax, linestyle=":")
ax.axvspan(dff.index[lckday], dff.index[lckday+nlckdays], alpha=0.1, color='red', label="_lockdown")
plt.text(dff.index[lckday+nlckdays-3], N*0.89, 'lockdown', color='red', alpha=0.5, rotation=90)
ax.set_title("SIR model")
ax.set_xlabel("")
ax.set_ylabel("# of people")
ax.grid(True, which="both")
dff.to_csv(os.path.join("data", "generated-sir.csv"))
plt.savefig(os.path.join("images", "generated-sir.png"), format="png", dpi=300)
plt.savefig(os.path.join("images", "generated-sir.pdf"), format="pdf", dpi=300, metadata=metadata)

fig, ax = plt.subplots(figsize=(8,6))
dff[["cases"]].plot(ax=ax)
dff[["forecast"]].plot(ax=ax, linestyle=":")
ax.axvspan(dff.index[lckday], dff.index[lckday+nlckdays], alpha=0.1, color='red', label="_lockdown")
plt.text(dff.index[lckday+1], N*0.89, 'lockdown', color='red', alpha=0.5, rotation=90)
ax.set_title("Cases forecasting")
ax.set_xlabel("")
ax.set_ylabel("# of occurences")
ax.grid(True, which="both")
plt.savefig(os.path.join("images", "generated-sir-cases.png"), format="png", dpi=300)
plt.savefig(os.path.join("images", "generated-sir-cases.pdf"), format="pdf", dpi=300, metadata=metadata)
