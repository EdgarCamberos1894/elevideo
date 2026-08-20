import apiClient from './client';

export const MAX_VIDEO_SIZE_MB = 200;
export const MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024;

export const validateVideoFile = (file) => {
  if (!file) {
    return { valid: false, message: 'Selecciona un archivo de video.' };
  }

  if (!file.type?.startsWith('video/')) {
    return { valid: false, message: 'El archivo seleccionado debe ser un video.' };
  }

  if (file.size > MAX_VIDEO_SIZE_BYTES) {
    return {
      valid: false,
      message: `El video supera el límite de ${MAX_VIDEO_SIZE_MB} MB. Selecciona un archivo más pequeño.`,
    };
  }

  return { valid: true, message: null };
};

export const videosApi = {
  // GET /api/v1/projects/{projectId}/videos - Listar videos del proyecto
  getByProject: async (projectId, params = {}) => {
    const response = await apiClient.get(`/api/v1/projects/${projectId}/videos`, { params });
    return response.data;
  },

  // GET /api/v1/projects/{projectId}/videos/{videoId} - Obtener video por ID
  getById: async (projectId, videoId) => {
    const response = await apiClient.get(`/api/v1/projects/${projectId}/videos/${videoId}`);
    return response.data;
  },

  // POST /api/v1/projects/{projectId}/videos - Subir video (multipart/form-data)
  create: async (projectId, formData, { onUploadProgress } = {}) => {
    const videoFile = formData.get('video');
    const validation = validateVideoFile(videoFile);

    if (!validation.valid) {
      const error = new Error(validation.message);
      error.isClientValidation = true;
      throw error;
    }

    const response = await apiClient.post(`/api/v1/projects/${projectId}/videos`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (!progressEvent.total || !onUploadProgress) return;

        const percentage = Math.min(
          100,
          Math.round((progressEvent.loaded * 100) / progressEvent.total)
        );
        onUploadProgress(percentage);
      },
    });
    return response.data;
  },

  // DELETE /api/v1/projects/{projectId}/videos/{videoId} - Eliminar video
  delete: async (projectId, videoId) => {
    const response = await apiClient.delete(`/api/v1/projects/${projectId}/videos/${videoId}`);
    return response.data;
  },
};
