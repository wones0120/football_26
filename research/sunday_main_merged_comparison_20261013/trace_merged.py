"""Reproduce a failed preliminary calculation on the immutable saved pool."""
from pathlib import Path
import json
from backend.app.product_services.preliminary_optimizer import PreliminaryOptimizerRequest,run_preliminary
request=PreliminaryOptimizerRequest.model_validate(json.loads(Path('research/sunday_main_merged_comparison_20261013/merged_request_v2.json').read_text()))
run_preliminary(request,run_id='d0cc8e65-0748-4356-8328-2a389aa96589')
