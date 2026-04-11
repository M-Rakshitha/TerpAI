#!/usr/bin/env python
"""
Curl test simulation showing all agents' current status with PlanetTerp & umd.io integration.
This test makes individual agent calls to verify API integration without timeout issues.
"""

import sys
import asyncio
import json

sys.path.insert(0, '.')

from backend.agents.dining_agent import run as dining_run
from backend.agents.schedule_agent import run as schedule_run
from backend.agents.study_resources_agent import run as study_run
from backend.agents.events_agent import run as events_run
from backend.agents.finance_agent import run as finance_run
from backend.agents.navigator_agent import run as navigator_run
from backend.agents.jobs_research_agent import run as jobs_run


async def test_all_agents():
    print('=' * 100)
    print('🧪 AGENT TEST: Verifying PlanetTerp & umd.io Integration')
    print('=' * 100)
    
    context = {
        'user_message': 'Study for organic chemistry, find dining options, check events, budget spending',
        'enriched_query': 'organic chemistry study resources dining vegan events budget',
        'course': 'CHEM231',
        'major': 'Chemistry',
        'budget': 50,
        'location': {'building': 'Times'},
    }
    
    agents = [
        ('Dining', dining_run, {'user_message': context['user_message'], 'dietary_preference': 'vegan', 'budget': context['budget'], 'location': context['location']}),
        ('Schedule', schedule_run, {'user_message': 'What MATH courses should I take?', 'enriched_query': 'mathematics', 'major': 'Chemistry'}),
        ('Study Resources', study_run, {'user_message': 'Find tutoring for CHEM231', 'enriched_query': 'chemistry tutoring', 'course': 'CHEM231'}),
        ('Events', events_run, {'user_message': 'What events this weekend?', 'enriched_query': 'events weekend',  'date': 'this weekend'}),
        ('Finance', finance_run, {'user_message': 'Budget for food, drinks, fun', 'enriched_query': 'budget spending', 'budget': context['budget']}),
        ('Navigator', navigator_run, {'query': 'Where is Times Building?', 'enriched_query': 'times building directions'}),
        ('Jobs', jobs_run, {'user_message': 'Find internships in chemistry', 'major': 'Chemistry'}),
    ]
    
    results = {}
    for agent_name, agent_fn, agent_context in agents:
        print(f'\n🔄 Testing {agent_name} agent...')
        try:
            result = await agent_fn(agent_context)
            
            # Harvest result info
            has_error = bool(result.get('error'))
            data_sources = result.get('data_sources', {})
            api_sources = data_sources.get('api_sources', [])
            
            # Determine result type
            if has_error:
                status = '⚠️ ERROR'
                detail = result['error'][:80]
            else:
                status = '✅ SUCCESS'
                detail = f"Sources: {', '.join(api_sources) if api_sources else 'web/gemini'}"
            
            results[agent_name] = {
                'status': status,
                'detail': detail,
                'data_sources': data_sources,
            }
            
            print(f'   {status}: {detail}')
            
        except Exception as e:
            results[agent_name] = {
                'status': '❌ FAILED',
                'detail': f'{type(e).__name__}',
                'error': str(e)[:80],
            }
            print(f'   ❌ FAILED: {type(e).__name__}')
    
    # Summary
    print('\n' + '=' * 100)
    print('📊 SUMMARY')
    print('=' * 100)
    
    successful = sum(1 for r in results.values() if 'SUCCESS' in r['status'])
    errors = sum(1 for r in results.values() if 'ERROR' in r['status'])
    failed = sum(1 for r in results.values() if 'FAILED' in r['status'])
    
    print(f'\nTotal Agents: {len(results)}')
    print(f'✅ Successful: {successful}')
    print(f'⚠️  Errors: {errors}')
    print(f'❌ Failed: {failed}')
    
    # Check API usage
    planetterp_used = False
    umdio_used = False
    for agent_name, data in results.items():
        data_sources = data.get('data_sources', {})
        api_sources = data_sources.get('api_sources', [])
        if 'planetterp' in api_sources:
            planetterp_used = True
        if 'umdio' in api_sources:
            umdio_used = True
    
    print(f'\n📡 Data Source Integration:')
    print(f'   {'✓' if planetterp_used else '✗'} PlanetTerp API usage detected')
    print(f'   {'✓' if umdio_used else '✗'} umd.io API usage detected')
    
    # Detailed results
    print(f'\n📋 Detailed Agent Results:')
    for agent_name, result in results.items():
        print(f'\n   {result["status"]} {agent_name}')
        print(f'      └─ {result["detail"]}')
        if result.get('data_sources'):
            sources_list = []
            if result['data_sources'].get('api_sources'):
                sources_list.append(f"APIs: {', '.join(result['data_sources']['api_sources'])}")
            if result['data_sources'].get('gemini_used'):
                sources_list.append('Gemini: ✓')
            if sources_list:
                print(f'      └─ {" | ".join(sources_list)}')
    
    print('\n' + '=' * 100)
    if successful >= 5:
        print('✅ TEST SUCCESSFUL - Most agents working with API integration')
    else:
        print('⚠️  TEST PARTIAL - Some agents need debugging')
    print('=' * 100)


if __name__ == '__main__':
    asyncio.run(test_all_agents())
