"""Save verified research context separately from all production configuration."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/classic_game_environment_review'

def main():
    r=json.loads((OUT/'historical_results.json').read_text())
    original=json.loads((ROOT/'artifacts/classic_game_total_analysis/results.json').read_text())['summary']
    for group in ('offense','QB','RB','WR','TE','DST'):
        for pop in ('field','top_10'):
            for key in ('selections','high','middle','low'):
                assert r['populations'][pop][group][key]==original['pooled'][group][pop][key]
    pop=r['populations'];top=pop['top_10']['offense'];field=pop['field']['offense']
    findings=[f"Top-10% lineups averaged {8*top['high']:.2f} offensive players from high-total games; field {8*field['high']:.2f}.",
        f"High-total RB selections: {100*pop['top_10']['RB']['high']:.1f}% versus {100*pop['field']['RB']['high']:.1f}% field.",
        f"Low-total DST selections: {100*pop['top_10']['DST']['low']:.1f}% versus {100*pop['field']['DST']['low']:.1f}% field.",
        f"Average selected offensive game total: {top['mean_game_total']:.2f} versus {field['mean_game_total']:.2f}; difference {top['mean_game_total']-field['mean_game_total']:.2f}.",
        "50+ total games had mixed outcomes: offensive selection share was lower than field in Weeks 1 and 3, higher in Week 2.",
        f"Mean offensive team implied points: {top['mean_team_implied']:.2f} versus {field['mean_team_implied']:.2f} field.",
        f"DST opponent implied points: {pop['top_10']['DST']['mean_opponent_implied']:.2f} versus {pop['field']['DST']['mean_opponent_implied']:.2f} field."]
    adjusted=[x for x in r['adjusted_associations'] if x['population']=='top_10' and x['weighting']=='entry' and x['adjusted']]
    controlled=["Exploratory lineup-level comparisons use contest intercepts, salary, prelock mean/P90 sums, position mix, QB/pass-catcher stacks, bring-backs and distinct games. No entry-level significance claims or production parameter fitting."]
    for x in adjusted:
        lo=min(x['by_slate'].values());hi=max(x['by_slate'].values())
        label,unit={'offensive_game_total':('Average offensive game O/U','one total point'),'offensive_team_implied':('Average offensive team implied points','one implied point'),'dst_opponent_implied':('DST opponent implied points','one implied point'),'high_total_rb_count':('High-total RB count','one additional RB')}[x['feature']]
        controlled.append(f"{label}: adjusted association {x['slope_percentage_points']:+.2f} percentage points per {unit} pooled, {x['slate_balanced_slope_percentage_points']:+.2f} with equal slate weights; individual-slate range {lo:+.2f} to {hi:+.2f}. Descriptive only.")
    controlled += ["The high-total RB association shrinks after projection/salary controls and changes sign across slates; independent predictive value is unestablished.",
        "Projected ownership was excluded: Week 1 has no recoverable prelock runs; Weeks 2–3 runs lack verified input provenance. Realized ownership is not a substitute.",
        "Rank archives support 46,661 top-5% entries and 9,380 top-1% entries, including ties. No archived payout records support an actual-cash comparison."]
    note={'contract_id':'classic_game_environment_research_notes_v1','title':'Classic game totals and historical finishing ranks',
        'label':r['label'],'verification':'Independently reproduced from hash-verified archived inputs',
        'sample_period':'2026 Weeks 1–3, Sunday Main','sample':{'contests':8,'independent_slates':3,'top_10_entries':93218,'field_entries':929532},
        'success_definition':'Top 10% means recorded rank <= ceil(full stored field size × 0.10), including all cutoff ties. Offensive selections count eight slots per classified legal roster; FLEX uses its actual position, DST is separate. Field includes top finishers.',
        'rows':[{'tier':title,'top_10':top[k],'field':field[k]} for k,title in [('high','Highest quarter'),('middle','Middle half'),('low','Lowest quarter')]],
        'findings':findings,'controlled_comparisons':controlled,'cash_outcomes':'Unavailable',
        'limitations':r['limitations']+['Top-decile finishes are not paid positions. Historical percentages are not requirements or selection bonuses.'],
        'source':{'path':'artifacts/classic_game_environment_review/historical_results.json','sha256':hashlib.sha256((OUT/'historical_results.json').read_bytes()).hexdigest(),'reproduced_at':'2026-10-09'}}
    (ROOT/'docs/product/classic_game_environment_research.json').write_text(json.dumps(note,indent=2)+'\n')
    print('Verified research note written.')

if __name__=='__main__':main()
