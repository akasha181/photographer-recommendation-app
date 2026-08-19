import { api, unwrap } from '../client';
import type {
  PortfolioAlbum,
  PortfolioImage,
} from '../../types/models';

export interface AlbumPage {
  items: PortfolioAlbum[];
  page: number;
  totalPages: number;
  hasNext: boolean;
}

interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const portfolioApi = {
  async albums(page = 1): Promise<AlbumPage> {
    const response = await api.get<any>('/api/v1/portfolio/albums/', {
      params: { page },
    });
    const data = response.data.data as PaginatedResponse<PortfolioAlbum>;

    const totalPages = Math.ceil(data.count / 20);
    return {
      items: data.results,
      page,
      totalPages,
      hasNext: data.next !== null,
    };
  },

  async albumDetail(albumId: number) {
    return unwrap<PortfolioAlbum>(
      api.get(`/api/v1/portfolio/albums/${albumId}/`),
    );
  },

  async images(albumId?: number, page = 1) {
    const params: Record<string, any> = { page };
    if (albumId) params.album_id = albumId;
    const response = await api.get<any>('/api/v1/portfolio/images/', {
      params,
    });
    const data = response.data.data as PaginatedResponse<PortfolioImage>;

    const totalPages = Math.ceil(data.count / 20);
    return {
      items: data.results,
      page,
      totalPages,
      hasNext: data.next !== null,
    };
  },

  async imageDetail(imageId: number) {
    return unwrap<PortfolioImage>(
      api.get(`/api/v1/portfolio/images/${imageId}/`),
    );
  },
};
