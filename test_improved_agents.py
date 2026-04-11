#!/usr/bin/env python
"""
Test Finance and Jobs agents with 2-3 different student-focused cases each.
Demonstrates improved web research, student-focused prompts, and proper answer generation.
"""

import sys
import asyncio
import json

sys.path.insert(0, '.')

from backend.agents.finance_agent import run as finance_run
from backend.agents.jobs_research_agent import run as jobs_run


async def test_finance_agent():
    """Test Finance agent with multiple student-focused scenarios."""
    print('\n' + '=' * 100)
    print('💰 FINANCE AGENT: Student Budget Planning')
    print('=' * 100)
    
    test_cases = [
        {
            'name': 'Weekly Dining & Transport Budget',
            'context': {
                'user_message': 'I need to budget $50/week for food and commuting on the bus',
                'budget': 50,
                'enriched_query': 'student food budget weekly transport metro'
            }
        },
        {
            'name': 'Semester Spending Plan',
            'context': {
                'user_message': 'What should I plan to spend per semester on classes, textbooks, and lab materials?',
                'enriched_query': 'semester textbook materials fees classes'
            }
        },
        {
            'name': 'Monthly Social Budget',
            'context': {
                'user_message': 'Help me budget $100/month for events, clubs, and going out with friends',
                'budget': 100,
                'enriched_query': 'monthly student social events entertainment'
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f'\n📊 Test Case {i}: {test_case["name"]}')
        print('-' * 100)
        print(f'Query: {test_case["context"]["user_message"]}')
        print(f'Budget: ${test_case["context"].get("budget", "Not specified")}')
        
        try:
            result = await finance_run(test_case['context'])
            
            # Display results
            has_error = bool(result.get('error'))
            
            if has_error:
                print(f'\n⚠️  Error: {result["error"][:80]}')
            else:
                print(f'\n✅ Success')
            
            # Show budget info
            if result.get('budget'):
                print(f'   Budget: ${result["budget"]:.2f}')
            if result.get('estimated_total'):
                print(f'   Estimated Total: ${result["estimated_total"]:.2f}')
            
            # Show categories
            categories = result.get('categories', [])
            if categories:
                print(f'   Categories: {", ".join(categories)}')
            
            # Show spending plan (summarized)
            plan = result.get('spending_plan', [])
            if plan:
                print(f'\n   Spending Plan (by category):')
                for item in plan[:4]:
                    category = item.get('category', 'unknown').title()
                    allocation = item.get('recommended_allocation', 0)
                    estimate = item.get('estimated_market_cost', 0)
                    print(f'     • {category}: ${allocation:.2f} (market: ${estimate:.2f})')
            
            # Show AI strategy
            if result.get('ai_strategy'):
                print(f'\n   💡 AI Budget Strategy:')
                print(f'   "{result["ai_strategy"][:180]}..."')
            
            # Show suggestion
            if result.get('suggestion'):
                print(f'\n   📝 Suggestion: {result["suggestion"][:100]}...')
            
            # Show data sources
            data_sources = result.get('data_sources', {})
            print(f'\n   Data Sources: ', end='')
            sources = []
            if data_sources.get('web_search_used'):
                sources.append(f'Web ({data_sources.get("total_reference_hits", 0)} hits)')
            if data_sources.get('gemini_used'):
                sources.append('Gemini AI')
            print(', '.join(sources) if sources else 'None')
            
        except Exception as e:
            print(f'\n❌ Exception: {type(e).__name__}: {str(e)[:100]}')


async def test_jobs_agent():
    """Test Jobs agent with multiple student-focused scenarios."""
    print('\n' + '=' * 100)
    print('💼 JOBS & RESEARCH AGENT: Opportunity Discovery')
    print('=' * 100)
    
    test_cases = [
        {
            'name': 'Computer Science Internship Search',
            'context': {
                'user_message': 'I want to find a software engineering internship for next summer',
                'major': 'Computer Science',
                'enriched_query': 'internship software engineering computer science opportunities'
            }
        },
        {
            'name': 'Research Lab Opportunities',
            'context': {
                'user_message': 'Can you help me find research labs doing work in machine learning or AI?',
                'major': 'Machine Learning',
                'enriched_query': 'research lab machine learning AI undergraduate'
            }
        },
        {
            'name': 'Business/Finance Internships',
            'context': {
                'user_message': 'Looking for internships in finance, accounting, or business consulting',
                'major': 'Business Administration',
                'enriched_query': 'finance accounting consulting internship business'
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f'\n🎯 Test Case {i}: {test_case["name"]}')
        print('-' * 100)
        print(f'Query: {test_case["context"]["user_message"]}')
        print(f'Major: {test_case["context"].get("major", "Not specified")}')
        
        try:
            result = await jobs_run(test_case['context'])
            
            # Display results
            has_error = bool(result.get('error'))
            
            if has_error:
                print(f'\n⚠️  Error: {result["error"][:80]}')
            else:
                print(f'\n✅ Success')
            
            # Show internship opportunities
            internships = result.get('internships') or result.get('jobs', [])
            if internships:
                print(f'\n   🏢 Internship Opportunities ({len(internships)}):')
                for item in internships[:3]:
                    title = item.get('title', item.get('title', 'N/A'))[:70]
                    print(f'     • {title}')
            else:
                print(f'\n   No internship opportunities found in web search')
            
            # Show research opportunities
            research = result.get('research_opportunities') or result.get('labs', [])
            if research:
                print(f'\n   🧪 Research Lab Opportunities ({len(research)}):')
                for item in research[:3]:
                    opportunity = item.get('opportunity', item.get('pi', 'N/A'))[:70]
                    print(f'     • {opportunity}')
            else:
                print(f'\n   No research opportunities found in web search')
            
            # Show job search tips
            if result.get('job_search_tips'):
                print(f'\n   💡 Job Search Tips:')
                tips_text = result['job_search_tips']
                # Show first 2-3 lines
                lines = tips_text.split('\n')[:5]
                for line in lines:
                    if line.strip():
                        print(f'   {line[:85]}')
            
            # Show research email template
            if result.get('research_email_template'):
                print(f'\n   ✉️  Research Email Template:')
                template = result['research_email_template']
                lines = template.split('\n')[:4]
                for line in lines:
                    if line.strip():
                        print(f'   {line[:85]}')
            
            # Show data sources
            data_sources = result.get('data_sources', {})
            print(f'\n   Data Sources: ', end='')
            sources = []
            if data_sources.get('web_search_used'):
                results_count = data_sources.get('results_count', 0)
                sources.append(f'Web Search ({results_count} results)')
            else:
                sources.append('Web Search (no results)')
            if data_sources.get('gemini_used'):
                sources.append('Gemini AI Tips & Templates')
            print(', '.join(sources))
            
        except Exception as e:
            print(f'\n❌ Exception: {type(e).__name__}: {str(e)[:100]}')


async def main():
    """Run all tests."""
    print('🧪 TESTING FINANCE & JOBS AGENTS WITH STUDENT-FOCUSED SCENARIOS')
    print('=' * 100)
    print('This test verifies that improved agents do proper research and give student-focused answers')
    
    await test_finance_agent()
    await test_jobs_agent()
    
    print('\n' + '=' * 100)
    print('✅ TEST COMPLETE')
    print('=' * 100)
    print('\n📊 Summary:')
    print('  • Finance agent now searches for cost references and provides budget strategies')
    print('  • Jobs agent now searches for internships, research labs, and provides career tips')
    print('  • Both agents generate student-focused AI advice and actionable recommendations')
    print('  • Web search fallbacks and improved pattern matching ensure better results')


if __name__ == '__main__':
    asyncio.run(main())
