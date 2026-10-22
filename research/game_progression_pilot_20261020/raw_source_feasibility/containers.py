"""Preserve nested converted R containers; missing values remain explicit nulls."""
from datetime import date,datetime
import math
import numpy as np
import pandas as pd

def plain(value):
    if value is None or value is pd.NA or value is pd.NaT:return None
    if isinstance(value,pd.DataFrame):
        return dict(__r_container__='DataFrame',**plain(value.to_dict(orient='split')))
    if isinstance(value,dict):return {str(k):plain(v)for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v)for v in value]
    if isinstance(value,np.ndarray):return plain(value.tolist())
    if isinstance(value,np.generic):return plain(value.item())
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,float)and not math.isfinite(value):return None
    if isinstance(value,(str,int,float,bool)):return value
    if isinstance(value,bytes):return value.decode('utf8')
    raise TypeError('Unsupported converted R container '+type(value).__name__)
