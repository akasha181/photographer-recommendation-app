/**
 * React Query hooks for the photographer's own studio — Modules 5 and 6.
 *
 * WHAT EACH MUTATION INVALIDATES
 * ------------------------------
 * These writes change what BUYERS see, not just what the owner sees. Editing
 * a service moves the "from Rs X" on every search card; blocking a week
 * closes dates in the booking form; featuring an image reorders the public
 * profile grid. So each mutation clears the public caches too — otherwise the
 * photographer changes something, opens their own public profile, and finds
 * it unchanged.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { qk } from '../../../api/queryKeys';
import {
  analyticsApi,
  myCalendarApi,
  myPortfolioApi,
  myServicesApi,
} from '../../../api/services/photographer.api';
import type {
  AvailabilityRule,
  ServicePackagePayload,
  ServiceWritePayload,
} from '../../../types/models';

/** Anything a buyer could be looking at that these writes change. */
function usePublicInvalidator() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: qk.photographers.all });
    queryClient.invalidateQueries({ queryKey: qk.availability.all });
    queryClient.invalidateQueries({ queryKey: qk.profile.me });
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// SERVICES
// ═══════════════════════════════════════════════════════════════════════════
export function useMyServices() {
  return useQuery({
    queryKey: qk.studio.services,
    queryFn: () => myServicesApi.list(),
    staleTime: 60_000,
  });
}

function useServiceMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  const invalidatePublic = usePublicInvalidator();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.studio.services });
      invalidatePublic();
    },
    retry: false,
  });
}

export function useCreateService() {
  return useServiceMutation((payload: ServiceWritePayload) =>
    myServicesApi.create(payload),
  );
}

export function useUpdateService() {
  return useServiceMutation(
    ({ id, payload }: { id: number; payload: Partial<ServiceWritePayload> }) =>
      myServicesApi.update(id, payload),
  );
}

export function useArchiveService() {
  return useServiceMutation((id: number) => myServicesApi.archive(id));
}

export function useRestoreService() {
  return useServiceMutation((id: number) => myServicesApi.restore(id));
}

export function useDeleteService() {
  return useServiceMutation((id: number) => myServicesApi.remove(id));
}

export function useAddPackage() {
  return useServiceMutation(
    ({ serviceId, payload }: { serviceId: number; payload: ServicePackagePayload }) =>
      myServicesApi.addPackage(serviceId, payload),
  );
}

export function useRemovePackage() {
  return useServiceMutation(
    ({ serviceId, packageId }: { serviceId: number; packageId: number }) =>
      myServicesApi.removePackage(serviceId, packageId),
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// CALENDAR
// ═══════════════════════════════════════════════════════════════════════════
export function useMyCalendar() {
  return useQuery({
    queryKey: qk.studio.calendar,
    queryFn: () => myCalendarApi.get(),
    staleTime: 60_000,
  });
}

function useCalendarMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  const invalidatePublic = usePublicInvalidator();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.studio.calendar });
      invalidatePublic();
    },
    retry: false,
  });
}

export function useSaveSchedule() {
  return useCalendarMutation((rules: Partial<AvailabilityRule>[]) =>
    myCalendarApi.saveSchedule(rules),
  );
}

export function useAddBlackout() {
  return useCalendarMutation(
    (payload: { start_date: string; end_date: string; reason?: string }) =>
      myCalendarApi.addBlackout(payload),
  );
}

export function useRemoveBlackout() {
  return useCalendarMutation((id: number) => myCalendarApi.removeBlackout(id));
}

// ═══════════════════════════════════════════════════════════════════════════
// PORTFOLIO
// ═══════════════════════════════════════════════════════════════════════════
export function useMyPortfolio() {
  return useQuery({
    queryKey: qk.studio.portfolio,
    queryFn: () => myPortfolioApi.images(),
    staleTime: 60_000,
  });
}

export function usePortfolioSummary() {
  return useQuery({
    queryKey: qk.studio.portfolioSummary,
    queryFn: () => myPortfolioApi.summary(),
    staleTime: 60_000,
  });
}

export function useMyAlbums() {
  return useQuery({
    queryKey: qk.studio.albums,
    queryFn: () => myPortfolioApi.albums(),
    staleTime: 60_000,
  });
}

function usePortfolioMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  const invalidatePublic = usePublicInvalidator();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.studio.all });
      invalidatePublic();
    },
    retry: false,
  });
}

export function useUploadImage() {
  return usePortfolioMutation(
    (payload: {
      file: { uri: string; name: string; type: string };
      caption?: string;
      album?: number | null;
    }) => myPortfolioApi.upload(payload),
  );
}

export function useToggleFeature() {
  return usePortfolioMutation((id: number) => myPortfolioApi.toggleFeature(id));
}

export function useDeleteImage() {
  return usePortfolioMutation((id: number) => myPortfolioApi.remove(id));
}

export function useCreateAlbum() {
  return usePortfolioMutation(
    (payload: { title: string; description?: string; is_public?: boolean }) =>
      myPortfolioApi.createAlbum(payload),
  );
}

export function useDeleteAlbum() {
  return usePortfolioMutation((id: number) => myPortfolioApi.removeAlbum(id));
}


// ═══════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════
export function useDashboard(days = 30, months = 6) {
  return useQuery({
    queryKey: qk.studio.dashboard(days, months),
    queryFn: () => analyticsApi.dashboard(days, months),
    // The headline numbers are computed live server-side, so a short stale
    // time keeps "pending requests" honest without hammering the endpoint.
    staleTime: 30_000,
  });
}
