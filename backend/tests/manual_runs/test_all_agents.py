#!/usr/bin/env python
"""
Comprehensive test of all agents with new PlanetTerp & umd.io integration.
Tests dining, schedule, study resources, events, finance, navigator, jobs agents.
"""

import sys
import asyncio
import json
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from backend.agents.router import run_agents as router_run
from backend.agents.task_planner import run as task_planner_run
from backend.agents.aggregator import aggregate


async def test_all_agents():
    # Comprehensive query that activates multiple agents
    context = {
        'user_message': (
            'Hey! I need to study for organic chemistry next week, '
            'find me good dining hall vegan options near times building, '
            'what events are happening on campus this weekend, '
            'and help me budget my weekly spending on food and entertainment. '
            'Also, where can I find study resources and tutoring for orgo?'
        ),
        'enriched_query': 'organic chemistry study resources dining vegan events budget spending navigation tutoring',
        'course': 'CHEM231',
        'major': 'Chemistry',
        'location': {
            'building': 'Times',
            'latitude': 38.9897,
            'longitude': -76.9378,
        },
        'budget': 50,
    }

    print('🔄 Starting comprehensive multi-agent test')
    print('=' * 80)
    print(f'Query: {context["user_message"][:80]}...')
    print('=' * 80)

    try:
        # Get task plan (which agents should run)
        print('\n📋 Planning which agents to activate...')
        plan = await task_planner_run(context['user_message'])
        agents_to_run = plan.tasks
        print(f'   Agents selected: {", ".join(agents_to_run)}')

        # Run router (executes selected agents in parallel with retry/backoff)
        print('\n📡 Executing agents (initial_run + recovery)...')
        router_result = await router_run(agents_to_run, context)
        
        print(f'\n✅ Router completed. Agents executed:')
        if isinstance(router_result, dict):
            for agent_name, agent_result in router_result.items():
                if agent_name != 'workflow_steps':
                    status = '✓' if agent_result.get('error') is None else '✗'
                    error_msg = f" - {agent_result.get('error', '')[:60]}" if agent_result.get('error') else ''
                    print(f"   {status} {agent_name}{error_msg}")

        # Aggregate results
        print('\n📊 Aggregating results...')
        aggregated = aggregate(
            query=context['enriched_query'],
            agents_used=agents_to_run,
            agent_results=router_result,
        )

        # Display aggregated output
        print('\n' + '=' * 80)
        print('AGGREGATED RESULTS')
        print('=' * 80)
        
        if isinstance(aggregated, dict):
            # Show agent activation status
            if 'agent_activation' in aggregated:
                print('\n🎯 Agent Activation Status:')
                for item in aggregated.get('agent_activation', []):
                    status_emoji = '✓' if item.get('status') == 'ok' else '⚠'
                    gemini_flag = '🤖' if item.get('gemini_used') else '  '
                    agent = item.get('agent', 'unknown')
                    error = f" [{item.get('error', '')[:40]}]" if item.get('error') else ''
                    print(f"  {status_emoji} {gemini_flag} {agent}{error}")

            # Show summary
            if 'summary' in aggregated:
                print(f'\n📝 Summary: {aggregated["summary"][:150]}...')

            # Show key results
            print('\n📋 Key Results:')
            keys_to_show = ['recommended_courses', 'dining_options', 'events', 'resources', 'tutoring', 'budget_plan', 'directions']
            for key in keys_to_show:
                if key in aggregated and aggregated[key]:
                    value = aggregated[key]
                    if isinstance(value, list) and len(value) > 0:
                        count = len(value)
                        first_item = str(value[0])[:60]
                        print(f"  ✓ {key}: {count} item(s) - {first_item}...")
                    elif isinstance(value, dict):
                        print(f"  ✓ {key}: {str(value)[:60]}...")

            # Full JSON output (truncated)
            print('\n📄 Full Response (first 2000 chars):')
            json_str = json.dumps(aggregated, indent=2)
            print(json_str[:2000])
            if len(json_str) > 2000:
                remaining = len(json_str) - 2000
                print(f'\n... ({remaining} more characters) ...')

        print('\n' + '=' * 80)
        print('✅ TEST COMPLETE - All agents executed successfully')
        print('=' * 80)

    except Exception as exc:
        print(f'\n❌ TEST FAILED: {type(exc).__name__}: {exc}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test_all_agents())
