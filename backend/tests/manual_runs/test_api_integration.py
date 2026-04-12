#!/usr/bin/env python
"""
Test PlanetTerp & umd.io API integration directly in schedule and study_resources agents.
"""

import sys
import asyncio
import json

sys.path.insert(0, '.')

from backend.utils.student_apis import (
    search_planetterp_courses, 
    get_umdio_courses,
    search_planetterp_professors,
    clear_cache,
)


async def test_apis_directly():
    print('=' * 100)
    print('🧪 DIRECT API TEST: PlanetTerp & umd.io')
    print('=' * 100)
    
    # Clear cache to ensure fresh API calls
    clear_cache()
    
    # Test 1: PlanetTerp course search
    print('\n1️⃣  PlanetTerp Course Search')
    print('-' * 100)
    try:
        courses = await search_planetterp_courses("MATH140", limit=3)
        if courses:
            print(f'✓ Found {len(courses)} course(s):')
            for course in courses:
                dept = course.get('department', 'N/A')
                num = course.get('number', 'N/A')
                title = course.get('title', 'N/A')
                print(f'  - {dept} {num}: {title}')
        else:
            print('✗ No courses found')
    except Exception as e:
        print(f'✗ Error: {type(e).__name__}: {e}')
    
    # Test 2: umd.io course search
    print('\n2️⃣  umd.io Course Search')
    print('-' * 100)
    try:
        courses = await get_umdio_courses(limit=3)
        if courses:
            print(f'✓ Found {len(courses)} course(s):')
            for course in courses[:3]:
                dept = course.get('department', 'N/A')
                num = course.get('number', 'N/A')
                title = course.get('title', 'N/A')
                print(f'  - {dept} {num}: {title}')
        else:
            print('✗ No courses found')
    except Exception as e:
        print(f'✗ Error: {type(e).__name__}: {e}')
    
    # Test 3: PlanetTerp professor search
    print('\n3️⃣  PlanetTerp Professor Search')
    print('-' * 100)
    try:
        profs = await search_planetterp_professors("David Mount", limit=3)
        if profs:
            print(f'✓ Found {len(profs)} professor(s):')
            for prof in profs:
                name = prof.get('name', prof.get('slug', 'N/A'))
                rating = prof.get('average_rating', 'N/A')
                print(f'  - {name} (Rating: {rating})  ')
        else:
            print('✗ No professors found')
    except Exception as e:
        print(f'✗ Error: {type(e).__name__}: {e}')
    
    # Test 4: Schedule agent with new integration
    print('\n4️⃣  Schedule Agent with PlanetTerp & umd.io')
    print('-' * 100)
    try:
        from backend.agents.schedule_agent import run as schedule_run
        result = await schedule_run({
            'user_message': 'What MATH courses should I take next semester?',
            'enriched_query': 'mathematics courses schedule',
            'major': 'Mathematics',
        })
        
        error = result.get('error')
        if error:
            print(f'⚠️  Agent returned error: {error[:100]}...')
        else:
            recommended = result.get('recommended_courses', [])
            data_sources = result.get('data_sources', {})
            print(f'✓ Agent completed successfully')
            print(f'  - Recommended courses: {len(recommended)}')
            print(f'  - Data sources: {data_sources}')
            if recommended:
                print(f'  - First course: {recommended[0].get("course_id", "N/A")} - {recommended[0].get("title", "N/A")}')
    except Exception as e:
        print(f'✗ Error: {type(e).__name__}: {e}')
    
    # Test 5: Study resources agent with new integration
    print('\n5️⃣  Study Resources Agent with PlanetTerp')
    print('-' * 100)
    try:
        from backend.agents.study_resources_agent import run as study_run
        result = await study_run({
            'user_message': 'Find me tutoring for CHEM231 organic chemistry',
            'enriched_query': 'organic chemistry tutoring resources',
            'course': 'CHEM231',
        })
        
        error = result.get('error')
        if error:
            print(f'⚠️  Agent returned error: {error[:100]}...')
        else:
            tutoring = result.get('tutoring', [])
            data_sources = result.get('data_sources', {})
            print(f'✓ Agent completed successfully')
            print(f'  - Tutoring services: {len(tutoring)}')
            print(f'  - Data sources: {data_sources}')
    except Exception as e:
        print(f'✗ Error: {type(e).__name__}: {e}')
    
    print('\n' + '=' * 100)
    print('✅ API Integration Test Complete')
    print('=' * 100)


if __name__ == '__main__':
    asyncio.run(test_apis_directly())
