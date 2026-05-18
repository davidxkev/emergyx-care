'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  Bed,
  CheckCircle2,
  Home,
  Pencil,
  Plus,
  Save,
  Trash2,
  UserRound,
  UsersRound,
  X,
} from 'lucide-react';

import { AdminSidebar } from '@/components/ui/admin-sidebar';
import { Button } from '@/components/ui/button';
import { DashboardHeader } from '@/components/ui/dashboard-header';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { confirmDestructiveAction } from '@/lib/confirm';
import { getCareContext, getHealth, updateCareContext } from '@/lib/api';
import { loadRoomDisplayNames } from '@/lib/room-names';
import type { CareContextRead, HealthResponse } from '@/lib/types';

const RESIDENTS_STORAGE_KEY = 'emergyx-residents-v1';

interface ResidentProfile {
  id: string;
  name: string;
  rooms: string[];
  context: string;
  createdAt: string;
  updatedAt: string;
}

interface SensorRoomOption {
  roomId: string;
  label: string;
  sensorCount: number;
  sensorIds: string[];
}

function formatRoomName(room?: string | null) {
  if (!room) {
    return 'Unassigned';
  }
  const displayNames = loadRoomDisplayNames();
  if (displayNames[room]) {
    return displayNames[room];
  }
  const autoRoomMatch = room.match(/^auto_room_(\d+)$/);
  if (autoRoomMatch) {
    return `Sensor Area ${autoRoomMatch[1]}`;
  }
  return room
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function loadResidents(): ResidentProfile[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(RESIDENTS_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return null;
        }
        const record = item as Partial<ResidentProfile>;
        const name = typeof record.name === 'string' ? record.name.trim() : '';
        if (!name) {
          return null;
        }
        return {
          id: typeof record.id === 'string' ? record.id : crypto.randomUUID(),
          name,
          rooms: Array.isArray(record.rooms)
            ? record.rooms.filter((room): room is string => typeof room === 'string' && room.length > 0)
            : [],
          context: typeof record.context === 'string' ? record.context : '',
          createdAt: typeof record.createdAt === 'string' ? record.createdAt : new Date().toISOString(),
          updatedAt: typeof record.updatedAt === 'string' ? record.updatedAt : new Date().toISOString(),
        };
      })
      .filter((item): item is ResidentProfile => Boolean(item));
  } catch {
    return [];
  }
}

function saveResidents(residents: ResidentProfile[]) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(RESIDENTS_STORAGE_KEY, JSON.stringify(residents));
}

function toResidentProfile(resident: CareContextRead['residents'][number]): ResidentProfile {
  return {
    id: resident.id,
    name: resident.name,
    rooms: resident.rooms,
    context: resident.context,
    createdAt: resident.created_at,
    updatedAt: resident.updated_at,
  };
}

function toResidentRead(resident: ResidentProfile): CareContextRead['residents'][number] {
  return {
    id: resident.id,
    name: resident.name,
    rooms: resident.rooms,
    context: resident.context,
    created_at: resident.createdAt,
    updated_at: resident.updatedAt,
  };
}

function buildSensorRoomOptions(
  health: HealthResponse | null,
  careContext: CareContextRead | null,
): SensorRoomOption[] {
  const assignments = careContext?.sensor_assignments ?? {};
  const roomMap = new Map<string, { sensorCount: number; sensorIds: string[] }>();

  for (const sensor of health?.fda2_sensors ?? []) {
    const roomId = assignments[sensor.sensor_id] ?? sensor.room;
    if (!roomId) {
      continue;
    }
    const current = roomMap.get(roomId) ?? { sensorCount: 0, sensorIds: [] };
    current.sensorCount += 1;
    current.sensorIds.push(sensor.sensor_id);
    roomMap.set(roomId, current);
  }

  return Array.from(roomMap.entries())
    .map(([roomId, value]) => ({
      roomId,
      label: formatRoomName(roomId),
      sensorCount: value.sensorCount,
      sensorIds: value.sensorIds,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function ResidentsDashboard() {
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [careContext, setCareContext] = useState<CareContextRead | null>(null);
  const [residents, setResidents] = useState<ResidentProfile[]>([]);
  const [residentName, setResidentName] = useState('');
  const [selectedRooms, setSelectedRooms] = useState<string[]>([]);
  const [residentContext, setResidentContext] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [editingResidentId, setEditingResidentId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editRooms, setEditRooms] = useState<string[]>([]);
  const [editContext, setEditContext] = useState('');
  const [savingResident, setSavingResident] = useState(false);

  const loadPage = useCallback(async () => {
    setError(null);
    const [healthPayload, contextPayload] = await Promise.all([
      getHealth(),
      getCareContext(),
    ]);
    setHealth(healthPayload);
    let nextContext = contextPayload;
    let nextResidents = contextPayload.residents.map(toResidentProfile);
    const localResidents = loadResidents();
    if (nextResidents.length === 0 && localResidents.length > 0) {
      const migrated = {
        ...contextPayload,
        residents: localResidents.map(toResidentRead),
      };
      const response = await updateCareContext(migrated);
      nextContext = response.context;
      nextResidents = response.context.residents.map(toResidentProfile);
    }
    setCareContext(nextContext);
    setResidents(nextResidents);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      try {
        setIsRefreshing(true);
        await loadPage();
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Unable to load residents.');
        }
      } finally {
        if (!cancelled) {
          setIsRefreshing(false);
        }
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [loadPage]);

  const roomOptions = useMemo(
    () => buildSensorRoomOptions(health, careContext),
    [health, careContext],
  );
  const filteredResidents = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return residents;
    }
    return residents.filter((resident) => {
      const roomLabels = resident.rooms.map(formatRoomName).join(' ');
      return `${resident.name} ${roomLabels} ${resident.context}`.toLowerCase().includes(query);
    });
  }, [residents, searchQuery]);

  const refreshResidents = async () => {
    try {
      setIsRefreshing(true);
      await loadPage();
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Unable to refresh residents.');
    } finally {
      setIsRefreshing(false);
    }
  };

  const exportResidents = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      residents,
      sensor_rooms: roomOptions,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'emergyx-residents.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const toggleRoom = (roomId: string) => {
    setSelectedRooms((current) =>
      current.includes(roomId)
        ? current.filter((item) => item !== roomId)
        : [...current, roomId],
    );
  };

  const persistResidents = async (nextResidents: ResidentProfile[]) => {
    const base = careContext ?? (await getCareContext());
    const response = await updateCareContext({
      ...base,
      residents: nextResidents.map(toResidentRead),
    });
    setCareContext(response.context);
    setResidents(response.context.residents.map(toResidentProfile));
    saveResidents(nextResidents);
  };

  const addResident = async () => {
    const name = residentName.trim();
    if (!name) {
      setFeedback('Add a resident name first.');
      return;
    }
    if (selectedRooms.length === 0) {
      setFeedback('Choose at least one monitored room for this resident.');
      return;
    }
    const now = new Date().toISOString();
    const nextResident: ResidentProfile = {
      id: crypto.randomUUID(),
      name,
      rooms: selectedRooms,
      context: residentContext.trim(),
      createdAt: now,
      updatedAt: now,
    };
    const next = [nextResident, ...residents];
    try {
      setSavingResident(true);
      await persistResidents(next);
      setResidentName('');
      setSelectedRooms([]);
      setResidentContext('');
      setFeedback(`${name} added with ${selectedRooms.length} monitored room${selectedRooms.length === 1 ? '' : 's'}.`);
    } catch (saveError) {
      setFeedback(saveError instanceof Error ? saveError.message : 'Unable to save resident.');
    } finally {
      setSavingResident(false);
    }
  };

  const deleteResident = async (residentId: string) => {
    const resident = residents.find((item) => item.id === residentId);
    const name = resident?.name ?? 'this resident';
    if (!confirmDestructiveAction(`Delete ${name}? This removes the resident profile and saved context.`)) {
      return;
    }
    const next = residents.filter((resident) => resident.id !== residentId);
    try {
      setSavingResident(true);
      await persistResidents(next);
      if (editingResidentId === residentId) {
        setEditingResidentId(null);
      }
      setFeedback('Resident removed.');
    } catch (saveError) {
      setFeedback(saveError instanceof Error ? saveError.message : 'Unable to delete resident.');
    } finally {
      setSavingResident(false);
    }
  };

  const startEditingResident = (resident: ResidentProfile) => {
    setEditingResidentId(resident.id);
    setEditName(resident.name);
    setEditRooms(resident.rooms);
    setEditContext(resident.context);
    setFeedback(null);
  };

  const cancelEditingResident = () => {
    setEditingResidentId(null);
    setEditName('');
    setEditRooms([]);
    setEditContext('');
  };

  const toggleEditRoom = (roomId: string) => {
    setEditRooms((current) =>
      current.includes(roomId)
        ? current.filter((item) => item !== roomId)
        : [...current, roomId],
    );
  };

  const saveEditedResident = async () => {
    const residentId = editingResidentId;
    const name = editName.trim();
    if (!residentId) {
      return;
    }
    if (!name) {
      setFeedback('Resident name cannot be empty.');
      return;
    }
    if (editRooms.length === 0) {
      setFeedback('Choose at least one monitored room for this resident.');
      return;
    }

    const next = residents.map((resident) =>
      resident.id === residentId
        ? {
            ...resident,
            name,
            rooms: editRooms,
            context: editContext.trim(),
            updatedAt: new Date().toISOString(),
          }
        : resident,
    );
    try {
      setSavingResident(true);
      await persistResidents(next);
      setFeedback(`${name} updated.`);
      cancelEditingResident();
    } catch (saveError) {
      setFeedback(saveError instanceof Error ? saveError.message : 'Unable to save resident.');
    } finally {
      setSavingResident(false);
    }
  };

  return (
    <SidebarProvider>
      <AdminSidebar />
      <SidebarInset>
        <DashboardHeader
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onRefresh={() => void refreshResidents()}
          onExport={exportResidents}
          isRefreshing={isRefreshing}
          searchPlaceholder="Search residents, rooms, or context..."
        />

        <div className="flex flex-1 flex-col gap-2 bg-[radial-gradient(circle_at_top_left,rgba(37,99,235,0.08),transparent_32rem),linear-gradient(180deg,var(--background),rgba(241,245,249,0.72))] p-2 pt-0 sm:gap-4 sm:p-4 dark:bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.18),transparent_30rem),linear-gradient(180deg,var(--background),#09090b)]">
          <div className="min-h-[calc(100vh-4rem)] flex-1 rounded-lg p-3 sm:rounded-xl sm:p-4 md:p-6">
            <div className="mx-auto max-w-6xl space-y-6">
              <section className="overflow-hidden rounded-3xl border border-border bg-card/80 p-6 shadow-sm md:p-8">
                <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.22em] text-blue-600 dark:text-blue-300">
                      Residents
                    </p>
                    <h1 className="mt-3 text-3xl font-bold tracking-tight md:text-4xl">
                      Resident Profiles
                    </h1>
                    <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground md:text-base">
                      Assign each resident to monitored rooms and add caregiver context
                      that can later be used by Gemma reports, summaries, and alerts.
                    </p>
                  </div>
                  <div className="grid gap-2 rounded-2xl border border-border bg-background/70 p-4 text-sm">
                    <div className="flex items-center justify-between gap-8">
                      <span className="text-muted-foreground">Residents</span>
                      <strong>{residents.length}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-8">
                      <span className="text-muted-foreground">Sensor rooms</span>
                      <strong>{roomOptions.length}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-8">
                      <span className="text-muted-foreground">Source</span>
                      <strong>Local browser</strong>
                    </div>
                  </div>
                </div>
              </section>

              {error ? (
                <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}

              <section className="grid gap-6 lg:grid-cols-5">
                <article className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm lg:col-span-2">
                  <div className="flex items-center gap-3">
                    <div className="rounded-xl bg-blue-500/10 p-3 text-blue-600 dark:text-blue-300">
                      <Plus className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
                        Add resident
                      </p>
                      <h2 className="text-2xl font-bold">Profile setup</h2>
                    </div>
                  </div>

                  <div className="mt-6 grid gap-4">
                    <label className="space-y-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                        Resident name
                      </span>
                      <input
                        className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                        onChange={(event) => setResidentName(event.target.value)}
                        placeholder="Example: Mom, Dad, Helen"
                        type="text"
                        value={residentName}
                      />
                    </label>

                    <div className="space-y-2">
                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                        Monitored rooms
                      </span>
                      {roomOptions.length ? (
                        <div className="grid gap-2">
                          {roomOptions.map((room) => (
                            <label
                              className="flex items-start gap-3 rounded-2xl border border-border bg-background/70 p-3 text-sm"
                              key={room.roomId}
                            >
                              <input
                                checked={selectedRooms.includes(room.roomId)}
                                className="mt-1"
                                onChange={() => toggleRoom(room.roomId)}
                                type="checkbox"
                              />
                              <span>
                                <span className="block font-semibold">{room.label}</span>
                                <span className="text-xs text-muted-foreground">
                                  {room.sensorCount} sensor{room.sensorCount === 1 ? '' : 's'}
                                </span>
                              </span>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <div className="rounded-2xl border border-dashed border-border bg-background/70 p-4 text-sm text-muted-foreground">
                          No sensor-backed rooms found yet. Add or auto-detect sensors on
                          the Sensors page first.
                        </div>
                      )}
                    </div>

                    <label className="space-y-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                        Resident and location context
                      </span>
                      <textarea
                        className="min-h-32 w-full rounded-xl border border-border bg-card px-3 py-2 text-sm"
                        onChange={(event) => setResidentContext(event.target.value)}
                        placeholder="Example: Bedroom sensor faces the bed. Resident normally wakes twice overnight. Uses walker near hallway."
                        value={residentContext}
                      />
                    </label>

                    <Button disabled={!roomOptions.length || savingResident} onClick={() => void addResident()} type="button">
                      <Save className="h-4 w-4" />
                      Add resident
                    </Button>

                    {feedback ? (
                      <p className="rounded-xl border border-border bg-background px-3 py-2 text-xs font-medium">
                        {feedback}
                      </p>
                    ) : null}
                  </div>
                </article>

                <article className="rounded-3xl border border-border bg-card/75 p-6 shadow-sm lg:col-span-3">
                  <div className="flex items-center gap-3">
                    <div className="rounded-xl bg-green-500/10 p-3 text-green-600 dark:text-green-300">
                      <UsersRound className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
                        Care context
                      </p>
                      <h2 className="text-2xl font-bold">Residents</h2>
                    </div>
                  </div>

                  <div className="mt-6 grid gap-4">
                    {filteredResidents.length ? (
                      filteredResidents.map((resident) => {
                        const isEditing = editingResidentId === resident.id;
                        return (
                          <div
                            className="rounded-3xl border border-border bg-background/70 p-5"
                            key={resident.id}
                          >
                            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                              <div className="flex items-start gap-3">
                                <div className="rounded-xl bg-card p-3 text-primary">
                                  <UserRound className="h-5 w-5" />
                                </div>
                                <div className="min-w-0 flex-1">
                                  {isEditing ? (
                                    <label className="block space-y-1">
                                      <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                                        Resident name
                                      </span>
                                      <input
                                        className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm"
                                        onChange={(event) => setEditName(event.target.value)}
                                        type="text"
                                        value={editName}
                                      />
                                    </label>
                                  ) : (
                                    <>
                                      <h3 className="text-lg font-bold">{resident.name}</h3>
                                      <p className="mt-1 text-xs text-muted-foreground">
                                        Updated {new Date(resident.updatedAt).toLocaleString()}
                                      </p>
                                    </>
                                  )}
                                </div>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {isEditing ? (
                                  <>
                                    <Button
                                      disabled={savingResident}
                                      onClick={() => void saveEditedResident()}
                                      size="sm"
                                      type="button"
                                    >
                                      <Save className="h-4 w-4" />
                                      Save
                                    </Button>
                                    <Button
                                      disabled={savingResident}
                                      onClick={cancelEditingResident}
                                      size="sm"
                                      type="button"
                                      variant="outline"
                                    >
                                      <X className="h-4 w-4" />
                                      Cancel
                                    </Button>
                                  </>
                                ) : (
                                  <>
                                    <Button
                                      onClick={() => startEditingResident(resident)}
                                      size="sm"
                                      type="button"
                                      variant="outline"
                                    >
                                      <Pencil className="h-4 w-4" />
                                      Edit
                                    </Button>
                                    <Button
                                      disabled={savingResident}
                                      onClick={() => void deleteResident(resident.id)}
                                      size="sm"
                                      type="button"
                                      variant="outline"
                                    >
                                      <Trash2 className="h-4 w-4" />
                                      Delete
                                    </Button>
                                  </>
                                )}
                              </div>
                            </div>

                            {isEditing ? (
                              <div className="mt-4 grid gap-4 rounded-2xl border border-border bg-card/80 p-4">
                                <div className="space-y-2">
                                  <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                                    Monitored rooms
                                  </span>
                                  <div className="grid gap-2 sm:grid-cols-2">
                                    {roomOptions.map((room) => (
                                      <label
                                        className="flex items-start gap-3 rounded-2xl border border-border bg-background/70 p-3 text-sm"
                                        key={room.roomId}
                                      >
                                        <input
                                          checked={editRooms.includes(room.roomId)}
                                          className="mt-1"
                                          onChange={() => toggleEditRoom(room.roomId)}
                                          type="checkbox"
                                        />
                                        <span>
                                          <span className="block font-semibold">{room.label}</span>
                                          <span className="text-xs text-muted-foreground">
                                            {room.sensorCount} sensor{room.sensorCount === 1 ? '' : 's'}
                                          </span>
                                        </span>
                                      </label>
                                    ))}
                                  </div>
                                </div>

                                <label className="space-y-1">
                                  <span className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                                    Resident and location context
                                  </span>
                                  <textarea
                                    className="min-h-28 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                                    onChange={(event) => setEditContext(event.target.value)}
                                    value={editContext}
                                  />
                                </label>
                              </div>
                            ) : (
                              <>
                                <div className="mt-4 flex flex-wrap gap-2">
                                  {resident.rooms.map((room) => (
                                    <span
                                      className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs font-semibold"
                                      key={room}
                                    >
                                      <Home className="h-3.5 w-3.5" />
                                      {formatRoomName(room)}
                                    </span>
                                  ))}
                                </div>

                                <div className="mt-4 rounded-2xl border border-border bg-card/80 p-4">
                                  <div className="flex items-start gap-3">
                                    <Bed className="mt-0.5 h-4 w-4 text-blue-500" />
                                    <p className="text-sm leading-6 text-muted-foreground">
                                      {resident.context || 'No resident context added yet.'}
                                    </p>
                                  </div>
                                </div>
                              </>
                            )}
                          </div>
                        );
                      })
                    ) : (
                      <div className="rounded-3xl border border-dashed border-border bg-background/70 p-8 text-center">
                        <CheckCircle2 className="mx-auto h-8 w-8 text-muted-foreground" />
                        <h3 className="mt-3 text-lg font-bold">No residents match this view</h3>
                        <p className="mt-2 text-sm text-muted-foreground">
                          Add a resident and assign one or more rooms that already have sensors.
                        </p>
                      </div>
                    )}
                  </div>
                </article>
              </section>
            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

export default ResidentsDashboard;
