import { useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '@/api/projects';
import { MAX_VIDEO_SIZE_MB, validateVideoFile, videosApi } from '@/api/videos';
import { Layout } from '@/components/Layout';
import { VideoPreviewModal } from '@/components/VideoPreviewModal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import {
  ArrowLeft,
  UploadCloud,
  Film,
  MoreVertical,
  Trash2,
  Loader2,
  Play,
  Wand2,
  FileVideo,
  HardDrive,
  Sparkles,
  Eye,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

const statusConfig = {
  UPLOADED: {
    label: 'Listo',
    className: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900 dark:text-emerald-100 dark:border-emerald-700',
    icon: '✓'
  },
  PROCESSING: {
    label: 'Procesando',
    className: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900 dark:text-blue-100 dark:border-blue-700 status-processing',
    icon: '◌'
  },
  READY: {
    label: 'Completado',
    className: 'bg-violet-100 text-violet-800 border-violet-300 dark:bg-violet-900 dark:text-violet-100 dark:border-violet-700',
    icon: '★'
  },
  COMPLETED: {
    label: 'Completado',
    className: 'bg-violet-100 text-violet-800 border-violet-300 dark:bg-violet-900 dark:text-violet-100 dark:border-violet-700',
    icon: '★'
  },
  FAILED: {
    label: 'Error',
    className: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-900 dark:text-red-100 dark:border-red-700',
    icon: '✕'
  },
};

function formatDuration(seconds) {
  if (!seconds) return '--:--';
  const totalSeconds = Math.floor(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function formatFileSize(bytes) {
  if (!bytes) return '--';
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

function VideoThumbnail({ video }) {
  const [isReady, setIsReady] = useState(false);
  const mediaClassName = `absolute inset-0 h-full w-full object-cover transition-opacity ${isReady ? 'opacity-100' : 'opacity-0'}`;

  return (
    <>
      <div className="absolute inset-0 flex items-center justify-center bg-slate-900">
        <Film className="h-12 w-12 text-white/55" />
      </div>
      {video.thumbnailUrl ? (
        <img
          src={video.thumbnailUrl}
          alt={`Vista previa de ${video.title}`}
          className={mediaClassName}
          onLoad={() => setIsReady(true)}
          onError={() => setIsReady(false)}
        />
      ) : video.videoUrl ? (
        <video
          src={video.videoUrl}
          className={mediaClassName}
          muted
          playsInline
          preload="metadata"
          onLoadedData={() => setIsReady(true)}
          aria-label={`Vista previa de ${video.title}`}
        />
      ) : null}
    </>
  );
}

export function ProjectPage() {
  const { projectId } = useParams();
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [videoTitle, setVideoTitle] = useState('');
  const [videoFile, setVideoFile] = useState(null);
  const [videoFileError, setVideoFileError] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();

  const { data: projectData, isLoading: projectLoading } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.getById(projectId),
  });

  const { data: videosData, isLoading: videosLoading } = useQuery({
    queryKey: ['videos', projectId],
    queryFn: () => videosApi.getByProject(projectId, { page: 0, size: 50 }),
  });

  const uploadMutation = useMutation({
    mutationFn: (formData) => videosApi.create(projectId, formData, {
      onUploadProgress: setUploadProgress,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['videos', projectId] });
      setIsUploadOpen(false);
      setVideoTitle('');
      setVideoFile(null);
      setVideoFileError('');
      setUploadProgress(0);
      if (fileInputRef.current) fileInputRef.current.value = '';
      toast.success('¡Video subido exitosamente!');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || error.message || 'Error al subir video');
      setUploadProgress(0);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (videoId) => videosApi.delete(projectId, videoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['videos', projectId] });
      setIsDeleteOpen(false);
      setSelectedVideo(null);
      toast.success('Video eliminado');
    },
    onError: (error) => {
      toast.error(error.response?.data?.message || 'Error al eliminar');
    },
  });

  const selectVideoFile = (file) => {
    const validation = validateVideoFile(file);

    if (!validation.valid) {
      setVideoFile(null);
      setVideoFileError(validation.message);
      setUploadProgress(0);
      if (fileInputRef.current) fileInputRef.current.value = '';
      toast.error(validation.message);
      return false;
    }

    setVideoFile(file);
    setVideoFileError('');
    setUploadProgress(0);

    if (!videoTitle) {
      setVideoTitle(file.name.replace(/\.[^/.]+$/, ''));
    }

    return true;
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!videoTitle) return;

    const validation = validateVideoFile(videoFile);
    if (!validation.valid) {
      setVideoFileError(validation.message);
      toast.error(validation.message);
      return;
    }

    const formData = new FormData();
    formData.append('title', videoTitle);
    formData.append('video', videoFile);

    setUploadProgress(0);
    await uploadMutation.mutateAsync(formData).catch(() => undefined);
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) selectVideoFile(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) selectVideoFile(file);
  };

  const project = projectData?.data || projectData;
  const videos = videosData?.data?.content || videosData?.content || [];

  return (
    <Layout>
      <div className="space-y-6 sm:space-y-7" data-testid="project-page">
        {/* Header */}
        <div className="space-y-3 sm:space-y-4">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
          >
            <ArrowLeft className="h-4 w-4 group-hover:-translate-x-1 transition-transform" />
            Volver a proyectos
          </Link>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between sm:gap-6">
            <div className="space-y-1">
              {projectLoading ? (
                <Skeleton className="h-10 w-64" />
              ) : (
                <>
                  <h1 className="font-outfit text-3xl font-bold tracking-tight sm:text-4xl">
                    {project?.name}
                  </h1>
                  {project?.description && (
                    <p className="text-muted-foreground text-lg">{project.description}</p>
                  )}
                </>
              )}
            </div>
            <Dialog open={isUploadOpen} onOpenChange={setIsUploadOpen}>
              <DialogTrigger asChild>
                <Button
                  size="lg"
                  variant="gradient"
                  data-testid="upload-video-button"
                >
                  <UploadCloud className="mr-2 h-5 w-5" />
                  Subir video
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-lg">
                <form onSubmit={handleUpload}>
                  <DialogHeader>
                    <DialogTitle className="font-outfit text-xl">Subir video</DialogTitle>
                    <DialogDescription>
                      Sube un video horizontal para convertirlo a formato vertical
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-6">
                    <div className="space-y-2">
                      <Label htmlFor="title">Título del video</Label>
                      <Input
                        id="title"
                        value={videoTitle}
                        onChange={(e) => setVideoTitle(e.target.value)}
                        placeholder="Ej: Tutorial de marketing"
                        className="h-11"
                        data-testid="video-title-input"
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="video-file">Archivo de video</Label>
                      <div
                        className={`relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                          videoFileError
                            ? 'border-destructive/70 bg-destructive/5'
                            : isDragging
                              ? 'border-purple-500 bg-purple-500/10'
                              : 'border-border hover:border-purple-500/50 hover:bg-muted/50'
                        }`}
                        onClick={() => fileInputRef.current?.click()}
                        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={handleDrop}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            fileInputRef.current?.click();
                          }
                        }}
                        role="button"
                        tabIndex={0}
                        aria-describedby="video-file-help"
                      >
                        <input
                          id="video-file"
                          ref={fileInputRef}
                          type="file"
                          accept="video/*"
                          onChange={handleFileChange}
                          className="hidden"
                          data-testid="video-file-input"
                        />
                        {videoFile ? (
                          <div className="space-y-3">
                            <div className="w-16 h-16 mx-auto rounded-xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center">
                              <FileVideo className="h-8 w-8 text-purple-500" />
                            </div>
                            <div>
                              <p className="font-medium truncate max-w-xs mx-auto">{videoFile.name}</p>
                              <p id="video-file-help" className="text-sm text-muted-foreground mt-1">
                                {formatFileSize(videoFile.size)}
                              </p>
                            </div>
                            <span className="inline-flex h-9 items-center rounded-md px-3 text-sm font-medium text-muted-foreground">
                              Cambiar archivo
                            </span>
                          </div>
                        ) : (
                          <div className="space-y-3">
                            <div className="w-16 h-16 mx-auto rounded-xl bg-muted flex items-center justify-center">
                              <UploadCloud className="h-8 w-8 text-muted-foreground" />
                            </div>
                            <div>
                              <p className="font-medium">
                                Arrastra tu video aquí o haz clic
                              </p>
                              <p id="video-file-help" className="text-sm text-muted-foreground mt-1">
                                MP4, MOV, AVI, WebM (máx. {MAX_VIDEO_SIZE_MB} MB)
                              </p>
                            </div>
                          </div>
                        )}
                      </div>
                      {videoFileError && (
                        <p className="text-sm text-destructive" role="alert">
                          {videoFileError}
                        </p>
                      )}
                    </div>
                    {uploadMutation.isPending && (
                      <div className="space-y-2" aria-live="polite">
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">
                            {uploadProgress < 100 ? 'Subiendo...' : 'Finalizando carga...'}
                          </span>
                          <span className="font-medium">{uploadProgress}%</span>
                        </div>
                        <Progress value={uploadProgress} className="h-2" />
                      </div>
                    )}
                  </div>
                  <DialogFooter>
                    <Button
                      type="submit"
                      variant="brand"
                      className="w-full"
                      disabled={!videoFile || !videoTitle || Boolean(videoFileError) || uploadMutation.isPending}
                      data-testid="upload-video-submit"
                    >
                      {uploadMutation.isPending ? (
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                      ) : (
                        <UploadCloud className="mr-2 h-5 w-5" />
                      )}
                      Subir video
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* Videos Grid */}
        {videosLoading ? (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[...Array(6)].map((_, i) => (
              <Card key={i} className="overflow-hidden">
                <Skeleton className="aspect-video w-full" />
                <CardHeader>
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-4 w-1/2 mt-2" />
                </CardHeader>
              </Card>
            ))}
          </div>
        ) : videos.length === 0 ? (
          <div className="relative">
            <div className="absolute inset-0 empty-state-bg rounded-3xl" />
            <Card className="relative text-center py-20 border-dashed border-2 bg-transparent">
              <CardContent className="space-y-6">
                <div className="relative inline-flex">
                  <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full blur-xl opacity-30 animate-pulse" />
                  <div className="relative p-6 rounded-full bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-purple-500/20">
                    <Film className="h-16 w-16 text-purple-500" />
                  </div>
                </div>
                <div className="space-y-2">
                  <h3 className="font-outfit text-2xl font-semibold">
                    Sube tu primer video
                  </h3>
                  <p className="text-muted-foreground max-w-sm mx-auto">
                    Sube un video horizontal y conviértelo automáticamente a formato vertical para TikTok, Instagram Reels y YouTube Shorts
                  </p>
                </div>
                <Button
                  size="lg"
                  variant="gradient"
                  onClick={() => setIsUploadOpen(true)}
                >
                  <Sparkles className="mr-2 h-5 w-5" />
                  Subir mi primer video
                </Button>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div
            className={videos.length === 1
              ? 'grid max-w-lg grid-cols-1 gap-5'
              : 'grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3 sm:gap-6'}
            data-testid="uploaded-videos-grid"
          >
            {videos.map((video) => {
              const status = statusConfig[video.status] || statusConfig.UPLOADED;

              return (
                <Card
                  key={video.id}
                  className="video-card card-3d overflow-hidden border-border/50 bg-card/50 backdrop-blur-sm group"
                  data-testid={`video-card-${video.id}`}
                >
                  {/* Thumbnail */}
                  <div className="relative aspect-video bg-gradient-to-br from-slate-800 to-slate-900 overflow-hidden">
                    <VideoThumbnail video={video} />

                    {/* Overlay */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100" />

                    {/* Play button */}
                    <div className="absolute inset-0 flex items-center justify-center opacity-100 transition-all sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                      <Button
                        size="icon"
                        className="w-14 h-14 rounded-full bg-white/90 hover:bg-white text-black shadow-xl hover:scale-110 transition-transform"
                        onClick={(e) => {
                          e.preventDefault();
                          setSelectedVideo(video);
                          setIsPreviewOpen(true);
                        }}
                        aria-label={`Reproducir ${video.title}`}
                        title="Reproducir video"
                      >
                        <Play className="h-6 w-6 ml-1" fill="currentColor" />
                      </Button>
                    </div>

                    {/* Duration badge */}
                    {video.durationInSeconds && (
                      <div className="absolute bottom-2 right-2 px-2 py-1 rounded-md bg-black/70 text-white text-xs font-medium backdrop-blur-sm">
                        {formatDuration(video.durationInSeconds)}
                      </div>
                    )}

                    {/* Status badge */}
                    <div className="absolute top-2 left-2">
                      <Badge className={`${status.className} border font-medium`}>
                        {status.icon} {status.label}
                      </Badge>
                    </div>

                    {/* Menu */}
                    <div className="absolute top-2 right-2 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 bg-black/50 hover:bg-black/70 text-white"
                            aria-label={`Acciones de ${video.title}`}
                            title="Acciones del video"
                          >
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => {
                            setSelectedVideo(video);
                            setIsPreviewOpen(true);
                          }}>
                            <Eye className="mr-2 h-4 w-4" />
                            Ver video
                          </DropdownMenuItem>
                          <DropdownMenuItem asChild>
                            <Link to={`/projects/${projectId}/videos/${video.id}`}>
                              <Wand2 className="mr-2 h-4 w-4" />
                              Procesar
                            </Link>
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => {
                              setSelectedVideo(video);
                              setIsDeleteOpen(true);
                            }}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            Eliminar
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>

                  {/* Content */}
                  <CardHeader className="space-y-2 p-4 sm:p-5">
                    <CardTitle className="font-outfit text-base line-clamp-1 group-hover:text-purple-500 transition-colors">
                      <Link to={`/projects/${projectId}/videos/${video.id}`}>
                        {video.title}
                      </Link>
                    </CardTitle>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      {video.width && video.height && (
                        <span className="flex items-center gap-1">
                          <span className="font-medium">{video.width}×{video.height}</span>
                        </span>
                      )}
                      {video.sizeInBytes && (
                        <span className="flex items-center gap-1">
                          <HardDrive className="h-3 w-3" />
                          {formatFileSize(video.sizeInBytes)}
                        </span>
                      )}
                    </div>
                    <Button asChild size="sm" variant="brand" className="w-full">
                      <Link to={`/projects/${projectId}/videos/${video.id}`}>
                        <Wand2 className="mr-2 h-4 w-4" />
                        Convertir a vertical
                      </Link>
                    </Button>
                  </CardHeader>
                </Card>
              );
            })}
          </div>
        )}

        {/* Video Preview Modal */}
        <VideoPreviewModal
          isOpen={isPreviewOpen}
          onClose={() => setIsPreviewOpen(false)}
          video={selectedVideo}
        />

        {/* Delete Alert */}
        <AlertDialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>¿Eliminar video?</AlertDialogTitle>
              <AlertDialogDescription>
                Esta acción no se puede deshacer. Se eliminará el video y todos sus procesamientos.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => deleteMutation.mutate(selectedVideo?.id)}
                className="bg-destructive hover:bg-destructive/90"
                data-testid="confirm-delete-video"
              >
                {deleteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Eliminar
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </Layout>
  );
}
