"""Fixed authored sensitivity cases, chosen by retained native source IDs."""


def cases(roles):
    ids={a['source_player_id']:a['player_master_id'] for a in roles['actors']}
    def request(label,donor,recipient,channel):
        return dict(assumption_id=label,donor_player_master_id=ids[donor],recipient_player_master_id=ids[recipient],
            channel=channel,fraction=.5,
            rationale='Authored half-vacancy accounting sensitivity only; no empirically estimated amount or likelihood')
    donor='00-0040242';recipient='00-0033699'
    return [dict(case_id='factual_out_no_replacement',assumptions=[]),
        dict(case_id='authored_half_known_vacancy',assumptions=[request('HALF_CARRIES',donor,recipient,'rush_attempts'),request('HALF_TARGETS',donor,recipient,'targets')]),
        dict(case_id='missing_recipient_reference',assumptions=[request('MISSING_RECIPIENT_COUNTS',donor,'00-0037256','rush_attempts')]),
        dict(case_id='missing_donor_reference',assumptions=[request('MISSING_DONOR_COUNTS','00-0032268','00-0039910','pass_attempts')]),
        dict(case_id='missing_recipient_current_role',assumptions=[request('MISSING_RECIPIENT_ROLE',donor,'00-0035567','rush_attempts')]),
        dict(case_id='questionable_not_factual_out',assumptions=[request('Q_CANNOT_DONATE','00-0033955',recipient,'rush_attempts')])]
