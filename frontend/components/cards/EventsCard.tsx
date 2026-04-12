'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useUser } from '@auth0/nextjs-auth0';
import { EventsResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface EventsCardProps {
  data: EventsResult;
}

type CalendarStatus = {
  authenticated: boolean;
  connected: boolean;
  configured?: boolean;
  error?: string;
};

const EventsCard: React.FC<EventsCardProps> = ({ data }) => {
  const { events } = data;
  const { user, isLoading: authLoading } = useUser();
  const [calendar, setCalendar] = useState<CalendarStatus | null>(null);
  const [busyIndex, setBusyIndex] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refreshCalendarStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/calendar/status', { cache: 'no-store' });
      const json = (await res.json()) as CalendarStatus;
      setCalendar(json);
    } catch {
      setCalendar({ authenticated: false, connected: false, error: 'status_unavailable' });
    }
  }, []);

  useEffect(() => {
    if (!authLoading && user) {
      void refreshCalendarStatus();
    } else if (!authLoading && !user) {
      setCalendar({ authenticated: false, connected: false });
    }
  }, [authLoading, user, refreshCalendarStatus]);

  const addToGoogleCalendar = async (index: number, event: (typeof events)[0]) => {
    setBusyIndex(index);
    setMessage(null);
    try {
      const res = await fetch('/api/calendar/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: event.title,
          location: event.location,
          start: event.start,
          description: `CampusPilot campus event. Tags: ${event.tags.join(', ')}`,
        }),
      });
      const json = (await res.json()) as { html_link?: string; detail?: string; ok?: boolean };
      if (!res.ok) {
        setMessage(typeof json.detail === 'string' ? json.detail : 'Could not add event');
        return;
      }
      setMessage(json.html_link ? 'Added — open your Google Calendar to confirm.' : 'Added to your Google Calendar.');
      if (json.html_link && typeof window !== 'undefined') {
        window.open(json.html_link, '_blank', 'noopener,noreferrer');
      }
    } catch {
      setMessage('Network error while adding the event.');
    } finally {
      setBusyIndex(null);
    }
  };

  return (
    <Card>
      <CardHeader className="space-y-2">
        <CardTitle>Upcoming Events</CardTitle>
        {!authLoading && user && calendar?.configured === false && (
          <p className="text-xs text-amber-800">
            Set <code className="rounded bg-slate-100 px-1">CALENDAR_LINK_SECRET</code> on the frontend and backend to enable
            Google Calendar.
          </p>
        )}
        {!authLoading && user && calendar?.authenticated && !calendar.connected && calendar.configured !== false && (
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-muted-foreground">Connect Google Calendar to add these events in one click.</p>
            <Button variant="outline" size="sm" asChild>
              <a href="/api/calendar/google/start">Connect Google Calendar</a>
            </Button>
          </div>
        )}
        {!authLoading && !user && (
          <p className="text-sm text-muted-foreground">
            <a href="/api/auth/login" className="font-medium text-[#E31937] underline">
              Log in
            </a>{' '}
            to add events to your Google Calendar.
          </p>
        )}
        {message && <p className="text-sm text-green-700">{message}</p>}
      </CardHeader>
      <CardContent className="space-y-3">
        {events.map((event, index) => (
          <div key={index} className="p-3 border rounded-lg">
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-semibold">{event.title}</h3>
              {event.free_food && <Badge variant="secondary">Free Food</Badge>}
            </div>
            <p className="text-sm text-gray-600">{event.location}</p>
            <p className="text-sm text-gray-500">{new Date(event.start).toLocaleString()}</p>
            <div className="flex flex-wrap gap-1 mt-2">
              {event.tags.map((tag, tagIndex) => (
                <Badge key={tagIndex} variant="outline" className="text-xs">
                  {tag}
                </Badge>
              ))}
            </div>
            {user && calendar?.connected && (
              <div className="mt-3">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={busyIndex !== null}
                  onClick={() => addToGoogleCalendar(index, event)}
                >
                  {busyIndex === index ? 'Adding…' : 'Add to Google Calendar'}
                </Button>
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

export default EventsCard;