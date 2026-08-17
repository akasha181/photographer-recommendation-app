/**
 * The photographer's own listings, calendar and portfolio — Modules 5 and 6.
 *
 * Every endpoint here is scoped server-side to the authenticated
 * photographer, so nothing in this file passes an owner id. A request that
 * names someone else's service or image gets a 404, not a 403 — its
 * existence is not leaked.
 */

import { api, unwrap } from '../client';
import { ENDPOINTS } from '../config';
import type {
  AvailabilityRule,
  Dashboard,
  Blackout,
  BlackoutResult,
  MyCalendar,
  OwnService,
  PortfolioAlbum,
  PortfolioImage,
  PortfolioSummary,
  ServicePackagePayload,
  ServiceWritePayload,
} from '../../types/models';

export const myServicesApi = {
  /** Includes archived listings — the owner needs them to restore. */
  list() {
    return unwrap<OwnService[]>(api.get(ENDPOINTS.catalog.myServices));
  },

  create(payload: ServiceWritePayload) {
    return unwrap<OwnService>(api.post(ENDPOINTS.catalog.myServices, payload));
  },

  update(id: number, payload: Partial<ServiceWritePayload>) {
    return unwrap<OwnService>(api.patch(ENDPOINTS.catalog.myService(id), payload));
  },

  /** Hides it from discovery; existing bookings keep pointing at it. */
  archive(id: number) {
    return unwrap<OwnService>(api.post(ENDPOINTS.catalog.archiveService(id), {}));
  },

  restore(id: number) {
    return unwrap<OwnService>(api.post(ENDPOINTS.catalog.restoreService(id), {}));
  },

  /** Refused by the server once the service has bookings — archive instead. */
  remove(id: number) {
    return api.delete(ENDPOINTS.catalog.myService(id));
  },

  addPackage(serviceId: number, payload: ServicePackagePayload) {
    return unwrap(api.post(ENDPOINTS.catalog.packages(serviceId), payload));
  },

  updatePackage(
    serviceId: number,
    packageId: number,
    payload: Partial<ServicePackagePayload>,
  ) {
    return unwrap(
      api.patch(ENDPOINTS.catalog.servicePackage(serviceId, packageId), payload),
    );
  },

  removePackage(serviceId: number, packageId: number) {
    return api.delete(ENDPOINTS.catalog.removePackage(serviceId, packageId));
  },
};

export const myCalendarApi = {
  get() {
    return unwrap<MyCalendar>(api.get(ENDPOINTS.myAvailability.calendar));
  },

  /**
   * The whole week in one PUT.
   *
   * Seven separate saves would leave a half-applied week if the connection
   * dropped partway, and the calendar would then mix the old pattern with
   * the new one.
   */
  saveSchedule(rules: Partial<AvailabilityRule>[]) {
    return unwrap<AvailabilityRule[]>(
      api.put(ENDPOINTS.myAvailability.schedule, { rules }),
    );
  },

  /** Returns how many existing bookings fall inside — it cancels none of them. */
  addBlackout(payload: {
    start_date: string;
    end_date: string;
    reason?: string;
  }) {
    return unwrap<BlackoutResult>(
      api.post(ENDPOINTS.myAvailability.addBlackout, payload),
    );
  },

  removeBlackout(id: number) {
    return api.delete(ENDPOINTS.myAvailability.removeBlackout(id));
  },

  blackouts() {
    return unwrap<Blackout[]>(api.get(ENDPOINTS.myAvailability.blackouts));
  },
};

export const myPortfolioApi = {
  images() {
    return unwrap<PortfolioImage[]>(api.get(ENDPOINTS.myPortfolio.images));
  },

  summary() {
    return unwrap<PortfolioSummary>(api.get(ENDPOINTS.myPortfolio.summary));
  },

  /**
   * Upload one image. EXIF is stripped server-side and three sizes generated.
   *
   * multipart — axios must NOT be given an explicit Content-Type, because the
   * boundary is generated with the FormData and setting the header by hand
   * strips it, leaving the server with an empty body.
   */
  upload(payload: {
    file: { uri: string; name: string; type: string };
    caption?: string;
    album?: number | null;
  }) {
    const form = new FormData();
    form.append('image', payload.file as unknown as Blob);
    if (payload.caption) form.append('caption', payload.caption);
    if (payload.album) form.append('album', String(payload.album));

    return unwrap<PortfolioImage>(
      api.post(ENDPOINTS.myPortfolio.images, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        transformRequest: (data) => data,
        // A 6 MB photo on 3G takes a while; the default 20s is not enough.
        timeout: 90_000,
      }),
    );
  },

  update(id: number, payload: { caption?: string; album?: number | null }) {
    return unwrap<PortfolioImage>(api.patch(ENDPOINTS.myPortfolio.image(id), payload));
  },

  /** Capped at 12 server-side — "everything featured" means nothing is. */
  toggleFeature(id: number) {
    return unwrap<PortfolioImage>(api.post(ENDPOINTS.myPortfolio.feature(id), {}));
  },

  remove(id: number) {
    return api.delete(ENDPOINTS.myPortfolio.image(id));
  },

  reorder(imageIds: number[]) {
    return unwrap<PortfolioImage[]>(
      api.post(ENDPOINTS.myPortfolio.reorder, { image_ids: imageIds }),
    );
  },

  albums() {
    return unwrap<PortfolioAlbum[]>(api.get(ENDPOINTS.myPortfolio.albums));
  },

  createAlbum(payload: { title: string; description?: string; is_public?: boolean }) {
    return unwrap<PortfolioAlbum>(
      api.post(ENDPOINTS.myPortfolio.createAlbum, payload),
    );
  },

  /** The album's images survive as loose uploads — there is no undo here. */
  removeAlbum(id: number) {
    return api.delete(ENDPOINTS.myPortfolio.removeAlbum(id));
  },
};


export const analyticsApi = {
  /**
   * The whole Dashboard screen in one request.
   *
   * Six separate calls would mean six spinners resolving at different times
   * on a screen that is read at a glance.
   */
  dashboard(days = 30, months = 6) {
    return unwrap<Dashboard>(
      api.get(ENDPOINTS.analytics.dashboard, { params: { days, months } }),
    );
  },
};
