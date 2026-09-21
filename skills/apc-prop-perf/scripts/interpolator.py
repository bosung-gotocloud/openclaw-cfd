import numpy as np
import pandas as pd
import sys
import os
from scipy.interpolate import LinearNDInterpolator, CloughTocher2DInterpolator, NearestNDInterpolator

sys.path.insert(0, os.path.dirname(__file__))
from database import APCDatabase


class APCInterpolator:
    """RPM/Speed 2D 보간 엔진 + 교차 프로펠러 보간.
    APC .dat 파일의 비정규 격자에 대응하기 위해 LinearNDInterpolator 사용.
    """

    def __init__(self, df):
        """
        df: DataFrame with columns [rpm, v, pe, ct, cp, pwr_hp, torque_lbft,
                                    thrust_lbf, pwr_w, torque_nm, thrust_n,
                                    thr_pwr, mach, reyn, fom]
        """
        self.df = df.copy()
        self.all_rpms = sorted(df['rpm'].unique())
        self.all_vs = sorted(df['v'].unique())

        # (rpm, v) coordinate points
        self.points = df[['rpm', 'v']].values

        self.metrics = [
            'pe', 'ct', 'cp', 'pwr_hp', 'torque_lbft', 'thrust_lbf',
            'pwr_w', 'torque_nm', 'thrust_n', 'thr_pwr', 'mach', 'reyn', 'fom'
        ]

        self.interpolators = {}
        # LinearNDInterpolator: convex hull 내부만 보간, 외부 NaN
        for metric in self.metrics:
            vals = df[metric].values
            interp = LinearNDInterpolator(self.points, vals)
            self.interpolators[metric] = interp

        # NearestNDInterpolator: fallback - convex hull 외부용
        self.nearest_interpolators = {}
        for metric in self.metrics:
            vals = df[metric].values
            interp = NearestNDInterpolator(self.points, vals)
            self.nearest_interpolators[metric] = interp

    def query(self, rpm, v):
        """RPM, V(mph) 지점에서의 보간값 반환.
        convex hull 내부: linear 보간, 외부: nearest neighbor.
        """
        point = np.array([[rpm, v]])
        results = {}
        for metric in self.metrics:
            linear_val = self.interpolators[metric](point)
            if linear_val is not None and not np.isnan(linear_val[0]):
                results[metric] = float(linear_val[0])
            else:
                # convex hull 외부 → nearest neighbor fallback
                nearest_val = self.nearest_interpolators[metric](point)
                if nearest_val is not None and not np.isnan(nearest_val[0]):
                    results[metric] = float(nearest_val[0])
                else:
                    results[metric] = None
        return results

    @staticmethod
    def interpolate_between_props(db, diameter, pitch, rpm, speed, metrics=None):
        """
        여러 프로펠러 간 보간.
        (diameter, pitch) 기준 가장 가까운 N개 프로펠러를 찾아 가중 평균.
        """
        if metrics is None:
            metrics = ['thrust_lbf', 'pwr_hp', 'torque_lbft', 'pe', 'ct', 'cp']

        all_props = db.get_all_props()
        if all_props.empty:
            return {m: None for m in metrics} | {'confidence': 0.0, 'n_used': 0}

        # 전체 D/P 매칭 가능한 props만 필터링 (신뢰도 높은 것들만)
        candidates = []
        for _, row in all_props.iterrows():
            d_dist = abs(row['diameter'] - diameter)
            p_dist = abs(row['pitch'] - pitch)
            total_dist = d_dist + p_dist
            candidates.append((total_dist, d_dist, p_dist, row))

        # 가장 가까운 N개 선택
        n_select = min(4, len(candidates))
        candidates.sort(key=lambda x: x[0])
        selected = candidates[:n_select]

        # 가중치 계산: 거리가 가까울수록 높은 가중치
        total_weight = 0.0
        combined = {m: 0.0 for m in metrics}

        for d_dist, p_dist, total_dist, row in selected:
            weight = 1.0 / (total_dist + 1e-6)
            total_weight += weight
            prop_df = db.get_propeller_data(row['diameter'], row['pitch'])
            interp = APCInterpolator(prop_df)
            res = interp.query(rpm, speed)
            for m in metrics:
                if res.get(m) is not None:
                    combined[m] += weight * res[m]

        # 가중 평균 계산: 모든 가중치의 합으로 나눔 (n_used로 나누지 않음)
        if total_weight > 0:
            for m in metrics:
                combined[m] /= total_weight
        
        combined['confidence'] = min(1.0, 1.0 / (selected[0][0] + 1e-6)) if selected else 0.0
        combined['n_used'] = n_select
        return combined
