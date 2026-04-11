#!/usr/bin/env python
"""
Comprehensive test of all agents with new PlanetTerp & umd.io integration.
Extended report showing detailed agent results and data sources.
"""

import sys
import asyncio
import json
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from backend.agents.router import run_agents as router_run
from backend.agents.task_planner import run as task_planner_run
from backend.agents.aggregator import aggregate


async def test_all_agents_detailed():
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

    print('=' * 100)
    print('🔬 COMPREHENSIVE MULTI-AGENT TEST WITH PLANETTERP & UMD.IO INTEGRATION')
    print('=' * 100)
    print(f'\n📝 User Query:\n   {context["user_message"]}')
    print(f'\n📍 Context:\n   Course: {context["course"]} | Major: {context["major"]} | Budget: ${context["budget"]}/week')
    print('\n' + '=' * 100)

    try:
        # Get task plan (which agents should run)
        print('\n📋 STEP 1: Task Planning')
        print('-' * 100)
        plan = await task_planner_run(context['user_message'])
        agents_to_run = plan.tasks
        print(f'✓ Agents activated: {", ".join(agents_to_run)}')
        print(f'✓ Priority: {plan.priority}')
        if plan.context.budget:
            print(f'✓ Budget constraint detected: ${plan.context.budget}')
        if plan.context.deadline_mentioned:
            print(f'✓ Deadline detected: Yes')

        # Run router (executes selected agents in parallel with retry/backoff)
        print('\n📡 STEP 2: Executing Agents in Parallel')
        print('-' * 100)
        router_result = await router_run(agents_to_run, context)
        
        print(f'\n✓ Execution completed. Agent results:\n')
        for agent_name, agent_result in router_result.items():
            if agent_name == 'workflow_steps':
                continue
            
            status_emoji = '✓' if agent_result.get('error') is None else '✗'
            print(f'\n   {status_emoji} {agent_name.upper()}:')
            
            # Show data sources used
            data_sources = agent_result.get('data_sources', {})
            if data_sources:
                source_list = []
                if data_sources.get('api_sources'):
                    source_list.append(f"APIs: {', '.join(data_sources['api_sources'])}")
                if data_sources.get('gemini_used'):
                    source_list.append('Gemini: ✓')
                if data_sources.get('web_search_used'):
                    source_list.append('Web Search: ✓')
                if source_list:
                    print(f'      └─ Data sources: {" | ".join(source_list)}')
            
            # Show workflow steps (retry/recovery)
            workflow = agent_result.get('workflow_steps', [])
            if workflow:
                steps_str = ' → '.join([s['step'] for s in workflow])
                print(f'      └─ Workflow: {steps_str}')
            
            # Show results count
            if agent_result.get('error'):
                print(f'      └─ Error: {agent_result["error"][:80]}...')
            else:
                # Count results  by examining different possible keys
                results_count = 0
                if agent_name == 'dining' and 'dining_options' in agent_result:
                    results_count = len(agent_result.get('dining_options', []))
                    print(f'      └─ Results: {results_count} dining options found')
                elif agent_name == 'schedule' and 'recommended_courses' in agent_result:
                    results_count = len(agent_result.get('recommended_courses', []))
                    print(f'      └─ Results: {results_count} course recommendations')
                elif agent_name == 'study_resources' and 'tutoring' in agent_result:
                    tutoring_count = len(agent_result.get('tutoring', []))
                    resource_count = len(agent_result.get('resources', []))
                    print(f'      └─ Results: {tutoring_count} tutoring services, {resource_count} resources')
                elif agent_name == 'events' and 'events' in agent_result:
                    results_count = len(agent_result.get('events', []))
                    print(f'      └─ Results: {results_count} events found')
                elif agent_name == 'finance' and 'budget_plan' in agent_result:
                    categories = len(agent_result.get('budget_plan', {}).get('categories', []))
                    print(f'      └─ Results: Budget plan with {categories} spending categories')
                elif agent_name == 'navigator' and 'directions' in agent_result:
                    print(f'      └─ Results: Navigation route generated')
                elif agent_name == 'jobs_research' and 'job_tips' in agent_result:
                    tips_count = len(agent_result.get('job_tips', []))
                    print(f'      └─ Results: {tips_count} job/career tips')
                else:
                    print(f'      └─ Results: Success')

        # Aggregate results
        print('\n📊 STEP 3: Aggregating Results')
        print('-' * 100)
        aggregated = aggregate(
            query=context['enriched_query'],
            agents_used=agents_to_run,
            agent_results=router_result,
        )

        # Show agent activation summary
        print(f'\n✓ Activation Summary:')
        activation_count = 0
        error_count = 0
        summary_text = ''
        
        if hasattr(aggregated, 'agent_activation'):
            for item in aggregated.agent_activation:
                if item.get('status') == 'ok' if isinstance(item, dict) else item.status == 'ok':
                    activation_count += 1
                elif item.get('status') == 'error' if isinstance(item, dict) else item.status == 'error':
                    error_count += 1
                    
        print(f'   - Agents ran successfully: {activation_count}')
        print(f'   - Agents with errors: {error_count}')
        
        if hasattr(aggregated, 'summary'):
            summary_text = aggregated.summary
            if isinstance(summary_text, str):
                print(f'   - Summary: {summary_text[:150]}...')

        # Show key data sources used
        print(f'\n✓ Data Source Integration:')
        planetterp_used = False
        umdio_used = False
        web_search_used = False
        
        for agent_name, agent_result in router_result.items():
            if agent_name == 'workflow_steps':
                continue
            data_sources = agent_result.get('data_sources', {})
            if data_sources.get('api_sources'):
                apis = data_sources.get('api_sources', [])
                if 'planetterp' in apis:
                    planetterp_used = True
                if 'umdio' in apis:
                    umdio_used = True
                if 'web_search' in apis:
                    web_search_used = True
        
        print(f'   {'✓' if planetterp_used else '✗'} PlanetTerp API used')
        print(f'   {'✓' if umdio_used else '✗'} umd.io API used')
        print(f'   {'✓' if web_search_used else '✗'} Web Search fallback used')

        print('\n' + '=' * 100)
        print('✅ TEST COMPLETE - All agents executed and data sources integrated')
        print('=' * 100)

    except Exception as exc:
        print(f'\n❌ TEST FAILED: {type(exc).__name__}: {exc}')
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test_all_agents_detailed())
