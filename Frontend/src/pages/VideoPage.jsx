import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { videosApi } from '@/api/videos';
import { processingApi } from '@/api/processing';
import { Layout } from '@/components/Layout';
import { VideoPreviewModal, TikTokIcon, InstagramIcon, YouTubeIcon } from '@/components/VideoPreviewModal';
import { ProcessingHelpPopover } from '@/components/ProcessingHelpPopover';
import { AdvancedProcessingOptions } from '@/components/AdvancedProcessingOptions';
import { notifyProcessingComplete } from '@/lib/notifications';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Wand2,
  Loader2,
  Download,
  Trash2,
  Clock,
  XCircle,
  Play,
  Film,
  Smartphone,
  Settings2,
  Sparkles,
  Eye,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Scissors,
} from 'lucide-react';
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

const platformBadgeStyles = {
  tiktok: { label: 'TikTok', className: 'bg-black text-white border-0' },
  instagram: { label: 'Instagram Reels', className: 'bg-gradient-to-r from-pink-500 via-purple-500 to-orange-500 text-white border-0' },
  instagram_reels: { label: 'Instagram Reels', className: 'bg-gradient-to-r from-pink-500 via-purple-500 to-orange-500 text-white border-0' },
  youtube_shorts: { label: 'YouTube Shorts', className: 'bg-red-600 text-white border-0' },
};

const qualityOptions = [
  { value: 'fast', label: 'Rápida', desc: 'Procesa antes y genera un archivo más ligero.' },
  { value: 'normal', label: 'Normal', desc: 'Balance recomendado entre detalle y tiempo.' },
  { value: 'high', label: 'Alta calidad', desc: 'Más detalle y seguimiento más fino en Smart Crop.' },
];

const backgroundModeOptions = [
  { value: 'smart_crop', label: 'Recorte inteligente', desc: 'IA detecta y sigue al sujeto principal.' },
  { value: 'blurred', label: 'Fondo difuminado', desc: 'Conserva todo el video con un fondo suave.' },
  { value: 'black', label: 'Barras negras', desc: 'Conserva el encuadre original sin distracciones.' },
];

const smartClipDurationModes = [
  {
    value: 'auto',
    label: 'Automática',
    desc: 'EleVideo elige el inicio, el cierre y la duración que mejor funcionan.',
    recommended: true,
  },
  {
    value: 'approximate',
    label: 'Aproximada',
    desc: 'Busca cerca de la duración que indiques y puede variar unos segundos para cerrar mejor.',
  },
  {
    value: 'exact',
    label: 'Exacta',
    desc: 'Respeta exactamente la duración que indiques.',
  },
];

const platformShortMaxDurations = {
  tiktok: 180,
  instagram: 180,
  youtube_shorts: 180,
};

const jobStatusConfig = {
  pending: { label: 'En cola', icon: Clock, className: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900 dark:text-amber-100 dark:border-amber-700' },
  processing: { label: 'Procesando', icon: RefreshCw, className: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900 dark:text-blue-100 dark:border-blue-700' },
  completed: { label: 'Completado', icon: CheckCircle, className: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900 dark:text-emerald-100 dark:border-emerald-700' },
  failed: { label: 'Error', icon: AlertCircle, className: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-900 dark:text-red-100 dark:border-red-700' },
  cancelled: { label: 'Cancelado', icon: XCircle, className: 'bg-gray-200 text-gray-800 border-gray-300 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-600' },
};

const videoStatusConfig = {
  UPLOADED: { label: 'Listo', className: 'text-emerald-600 dark:text-emerald-400' },
  PROCESSING: { label: 'Procesando', className: 'text-blue-600 dark:text-blue-400' },
  READY: { label: 'Completado', className: 'text-violet-600 dark:text-violet-400' },
  COMPLETED: { label: 'Completado', className: 'text-violet-600 dark:text-violet-400' },
  FAILED: { label: 'Error', className: 'text-red-600 dark:text-red-400' },
};

const jobPhaseLabels = {
  queued: 'Esperando turno',
  validating: 'Validando solicitud',
  downloading: 'Descargando video',
  download_complete: 'Descarga completada',
  selecting_segment: 'Buscando el mejor momento',
  cutting_segment: 'Preparando el clip',
  segment_complete: 'Clip preparado',
  analyzing: 'Preparando análisis',
  detecting_faces: 'Analizando sujetos y encuadre',
  analysis_complete: 'Análisis completado',
  processing: 'Preparando video vertical',
  stabilizing: 'Estabilizando encuadre',
  cropping: 'Aplicando recorte inteligente',
  encoding: 'Generando video final',
  encoding_complete: 'Video generado',
  uploading: 'Subiendo resultado',
  upload_complete: 'Resultado subido',
  cleaning_up: 'Finalizando',
  completed: 'Completado',
  failed: 'Procesamiento fallido',
};

const ACTIVE_JOB_STATUSES = new Set(['pending', 'processing']);
const isActiveJob = (job) => ACTIVE_JOB_STATUSES.has(job.status?.toLowerCase());
const ACTIVE_JOB_POLL_INTERVAL_MS = 1800;
const JOBS_VISIBLE_LIMIT = 10;
const SHORT_MIN_DURATION_SECONDS = 5;
const SHORT_MAX_DURATION_SECONDS = 180;

const processingModeLabels = {
  vertical: 'Video completo',
  short_auto: 'Clip automático',
  short_manual: 'Clip manual',
};

const qualityLabels = {
  fast: 'Rápida',
  normal: 'Normal',
  high: 'Alta',
};

const backgroundLabels = {
  smart_crop: 'Recorte IA',
  blurred: 'Fondo difuminado',
  black: 'Barras negras',
};

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  const m = Math.floor(diff / 60);
  const h = Math.floor(diff / 3600);
  const d = Math.floor(diff / 86400);
  if (m < 1) return 'ahora';
  if (m < 60) return `hace ${m} min`;
  if (h < 24) return `hace ${h} h`;
  return `hace ${d} d`;
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '--:--';
  const totalSeconds = Math.max(0, Math.floor(Number(seconds)));
  const minutes = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function clampProgress(value) {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function getPlatformIcon(platform) {
  if (platform === 'tiktok') return TikTokIcon;
  if (platform === 'instagram' || platform === 'instagram_reels') return InstagramIcon;
  return YouTubeIcon;
}

export function VideoPage() {
  const { projectId, videoId } = useParams();
  const queryClient = useQueryClient();
  const prevJobsRef = useRef([]);
  const resultsSectionRef = useRef(null);

  const [processingMode, setProcessingMode] = useState('vertical');
  const [platform, setPlatform] = useState('tiktok');
  const [quality, setQuality] = useState('normal');
  const [backgroundMode, setBackgroundMode] = useState('smart_crop');
  const [shortAutoDurationMode, setShortAutoDurationMode] = useState('auto');
  const [shortAutoDuration, setShortAutoDuration] = useState(30);
  const [shortStartTime, setShortStartTime] = useState(0);
  const [shortDuration, setShortDuration] = useState(30);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedOptions, setAdvancedOptions] = useState({});
  const [activeTab, setActiveTab] = useState('renditions');

  const [isDeleteRenditionOpen, setIsDeleteRenditionOpen] = useState(false);
  const [selectedRendition, setSelectedRendition] = useState(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [previewVideo, setPreviewVideo] = useState(null);
  const [previewRendition, setPreviewRendition] = useState(null);

  const showProcessingTab = () => {
    setActiveTab('jobs');
    window.requestAnimationFrame(() => {
      resultsSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const { data: videoData, isLoading: videoLoading } = useQuery({
    queryKey: ['video', projectId, videoId],
    queryFn: () => videosApi.getById(projectId, videoId),
  });

  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ['jobs', projectId, videoId],
    queryFn: () => processingApi.getJobs(projectId, videoId, { page: 0, size: JOBS_VISIBLE_LIMIT }),
    refetchInterval: (query) => {
      const currentJobs = query.state.data?.data?.content || query.state.data?.content || [];
      return currentJobs.some(isActiveJob) ? ACTIVE_JOB_POLL_INTERVAL_MS : false;
    },
    refetchIntervalInBackground: false,
  });

  const { data: renditionsData, isLoading: renditionsLoading, refetch: refetchRenditions } = useQuery({
    queryKey: ['renditions', projectId, videoId],
    queryFn: () => processingApi.getRenditions(projectId, videoId, { page: 0, size: 20 }),
  });

  const videoDurationSeconds = Math.max(
    0,
    Math.floor(Number(videoData?.data?.durationInSeconds ?? videoData?.durationInSeconds ?? 0)),
  );
  const hasVideoDuration = videoDurationSeconds > 0;
  const selectedPlatformMaxDuration = platformShortMaxDurations[platform] ?? SHORT_MAX_DURATION_SECONDS;
  const shortModesDisabled = hasVideoDuration && videoDurationSeconds < SHORT_MIN_DURATION_SECONDS;
  const shortAutoMaxDuration = hasVideoDuration
    ? Math.min(selectedPlatformMaxDuration, Math.max(SHORT_MIN_DURATION_SECONDS, videoDurationSeconds))
    : selectedPlatformMaxDuration;
  const maxManualStartTime = hasVideoDuration
    ? Math.max(0, videoDurationSeconds - SHORT_MIN_DURATION_SECONDS)
    : 0;
  const manualRemainingDuration = hasVideoDuration
    ? Math.max(0, videoDurationSeconds - shortStartTime)
    : selectedPlatformMaxDuration;
  const shortManualMaxDuration = Math.max(
    SHORT_MIN_DURATION_SECONDS,
    Math.min(selectedPlatformMaxDuration, Math.floor(manualRemainingDuration)),
  );

  const handleShortStartTimeChange = (rawValue) => {
    const parsedValue = Number(rawValue);
    if (!Number.isFinite(parsedValue)) {
      setShortStartTime(0);
      return;
    }
    const upperBound = hasVideoDuration ? maxManualStartTime : Math.max(0, parsedValue);
    setShortStartTime(Math.min(Math.max(parsedValue, 0), upperBound));
  };

  useEffect(() => {
    if (!hasVideoDuration) return;
    if (shortModesDisabled) {
      setProcessingMode((currentMode) => currentMode === 'vertical' ? currentMode : 'vertical');
      setShortAutoDuration(SHORT_MIN_DURATION_SECONDS);
      setShortStartTime(0);
      setShortDuration(SHORT_MIN_DURATION_SECONDS);
      return;
    }
    setShortAutoDuration((currentDuration) => (
      Math.min(Math.max(currentDuration, SHORT_MIN_DURATION_SECONDS), shortAutoMaxDuration)
    ));
    setShortStartTime((currentStart) => Math.min(Math.max(currentStart, 0), maxManualStartTime));
  }, [hasVideoDuration, maxManualStartTime, shortAutoMaxDuration, shortModesDisabled]);

  useEffect(() => {
    if (!hasVideoDuration || shortModesDisabled) return;
    setShortDuration((currentDuration) => (
      Math.min(Math.max(currentDuration, SHORT_MIN_DURATION_SECONDS), shortManualMaxDuration)
    ));
  }, [hasVideoDuration, shortManualMaxDuration, shortModesDisabled]);

  useEffect(() => {
    const jobs = jobsData?.data?.content || jobsData?.content || [];
    const prevJobs = prevJobsRef.current;
    let completedTransitionDetected = false;

    jobs.forEach((job) => {
      const prevJob = prevJobs.find((p) => (p.id || p.jobId) === (job.id || job.jobId));
      const status = job.status?.toLowerCase();
      const prevStatus = prevJob?.status?.toLowerCase();
      if (prevJob && prevStatus !== status && (status === 'completed' || status === 'failed')) {
        notifyProcessingComplete(videoData?.data?.title || 'Video', status);
        if (status === 'completed') completedTransitionDetected = true;
      }
    });

    if (completedTransitionDetected) {
      const stillHasActiveJobs = jobs.some(isActiveJob);
      void refetchRenditions().then(() => {
        if (!stillHasActiveJobs) {
          setActiveTab((currentTab) => currentTab === 'jobs' ? 'renditions' : currentTab);
        }
      });
    }
    prevJobsRef.current = jobs;
  }, [jobsData, videoData, refetchRenditions]);

  const processMutation = useMutation({
    mutationFn: (data) => processingApi.createJob(projectId, videoId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', projectId, videoId] });
      showProcessingTab();
      toast.success('¡Procesamiento iniciado! Puedes seguir el progreso en Procesos.');
    },
    onError: (error) => toast.error(error.response?.data?.message || 'Error al iniciar procesamiento'),
  });

  const cancelJobMutation = useMutation({
    mutationFn: (jobId) => processingApi.cancelJob(projectId, videoId, jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', projectId, videoId] });
      toast.success('Proceso cancelado');
    },
    onError: (error) => toast.error(error.response?.data?.message || 'Error al cancelar'),
  });

  const deleteRenditionMutation = useMutation({
    mutationFn: (renditionId) => processingApi.deleteRendition(projectId, videoId, renditionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['renditions', projectId, videoId] });
      setIsDeleteRenditionOpen(false);
      toast.success('Resultado eliminado');
    },
    onError: (error) => toast.error(error.response?.data?.message || 'Error al eliminar'),
  });

  const handleProcess = () => {
    const isShortMode = processingMode === 'short_auto' || processingMode === 'short_manual';
    if (isShortMode && shortModesDisabled) {
      toast.error(`El video debe durar al menos ${SHORT_MIN_DURATION_SECONDS} segundos para crear un short.`);
      return;
    }
    if (
      processingMode === 'short_auto'
      && shortAutoDurationMode !== 'auto'
      && shortAutoDuration > selectedPlatformMaxDuration
    ) {
      toast.error(`La duración objetivo no puede superar ${formatDuration(selectedPlatformMaxDuration)} para esta plataforma.`);
      return;
    }
    if (
      hasVideoDuration
      && processingMode === 'short_auto'
      && shortAutoDurationMode !== 'auto'
      && shortAutoDuration > videoDurationSeconds
    ) {
      toast.error('La duración objetivo no puede superar la duración del video.');
      return;
    }
    if (processingMode === 'short_manual' && shortDuration > selectedPlatformMaxDuration) {
      toast.error(`La duración del clip no puede superar ${formatDuration(selectedPlatformMaxDuration)} para esta plataforma.`);
      return;
    }
    if (hasVideoDuration && processingMode === 'short_manual' && shortStartTime + shortDuration > videoDurationSeconds) {
      toast.error('El corte manual no puede terminar después del final del video.');
      return;
    }

    const data = { processingMode, platform, quality, backgroundMode };
    if (processingMode === 'short_auto') {
      data.shortAutoDurationMode = shortAutoDurationMode;
      if (shortAutoDurationMode !== 'auto') {
        data.shortAutoDuration = shortAutoDuration;
      }
    } else if (processingMode === 'short_manual') {
      data.shortOptions = { startTime: shortStartTime, duration: shortDuration };
    }
    if (showAdvanced && Object.keys(advancedOptions).length > 0) {
      data.advancedOptions = advancedOptions;
    }
    processMutation.mutate(data);
  };

  const video = videoData?.data || videoData;
  const videoStatus = videoStatusConfig[video?.status] || videoStatusConfig.UPLOADED;
  const rawJobs = jobsData?.data?.content || jobsData?.content || [];
  const jobs = rawJobs.slice(0, JOBS_VISIBLE_LIMIT);
  const jobsTotal = Number(jobsData?.data?.totalElements ?? jobsData?.totalElements ?? jobs.length);
  const renditions = renditionsData?.data?.content || renditionsData?.content || [];
  const activeJobs = jobs.filter(isActiveJob);

  const openRenditionPreview = (rendition) => {
    setPreviewVideo(video);
    setPreviewRendition(rendition);
    setIsPreviewOpen(true);
  };

  return (
    <Layout>
      <div className="space-y-6 sm:space-y-8" data-testid="video-page">
        <div className="space-y-3 sm:space-y-4">
          <Link to={`/projects/${projectId}`} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group">
            <ArrowLeft className="h-4 w-4 group-hover:-translate-x-1 transition-transform" />
            Volver al proyecto
          </Link>
          {videoLoading ? <Skeleton className="h-10 w-64" /> : (
            <h1 className="font-outfit text-3xl sm:text-4xl font-bold tracking-tight break-words">{video?.title}</h1>
          )}
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:items-start lg:gap-8">
          <section className="order-1 space-y-5 lg:col-span-2 lg:col-start-1 lg:row-start-1 lg:space-y-6">
            {videoLoading ? (
              <Skeleton className="aspect-video w-full rounded-2xl" />
            ) : video?.videoUrl ? (
              <div className="relative aspect-video bg-black rounded-2xl overflow-hidden shadow-2xl">
                <video src={video.videoUrl} controls className="w-full h-full object-contain" data-testid="video-player" poster={video.thumbnailUrl} />
              </div>
            ) : (
              <div className="aspect-video bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl flex items-center justify-center">
                <Film className="h-20 w-20 text-white/20" />
              </div>
            )}

            {video && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
                {[
                  { label: 'Duración', value: formatDuration(video.durationInSeconds) },
                  { label: 'Resolución', value: `${video.width}×${video.height}` },
                  { label: 'Formato', value: (video.format || 'MP4').toUpperCase() },
                  { label: 'Estado', value: videoStatus.label, statusClassName: videoStatus.className },
                ].map((item) => (
                  <div key={item.label} className="stat-card rounded-xl p-3 sm:p-4">
                    <p className="text-xs sm:text-sm text-muted-foreground">{item.label}</p>
                    <p className={`font-semibold font-outfit text-sm sm:text-base truncate ${item.statusClassName || ''}`}>{item.value}</p>
                  </div>
                ))}
              </div>
            )}
          </section>

          <aside className="order-3 lg:col-start-3 lg:row-start-1 lg:row-span-2">
            <Card className="border-border/50 bg-card dark:bg-card/95 shadow-xl overflow-hidden lg:sticky lg:top-24">
              <CardHeader className="pb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-purple-500/20">
                    <Wand2 className="h-5 w-5 text-white" />
                  </div>
                  <div className="min-w-0">
                    <CardTitle className="font-outfit text-lg">Procesar video</CardTitle>
                    <CardDescription className="text-xs">Configura el resultado de arriba hacia abajo</CardDescription>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="space-y-5">
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <Label className="text-sm font-medium">1. ¿Qué quieres crear?</Label>
                  </div>
                  <div className="grid gap-2">
                    {[
                      { value: 'vertical', label: 'Video completo', desc: 'Procesa todo el video', icon: '📹' },
                      { value: 'short_auto', label: 'Short automático', desc: 'Busca el momento con mayor interés', icon: '✨' },
                      { value: 'short_manual', label: 'Short manual', desc: 'Tú eliges el tramo exacto', icon: '✂️' },
                    ].map((mode) => {
                      const isUnavailableShortMode = mode.value !== 'vertical' && shortModesDisabled;
                      return (
                        <div key={mode.value} className="relative">
                          <button
                            type="button"
                            disabled={isUnavailableShortMode}
                            aria-disabled={isUnavailableShortMode}
                            onClick={() => { if (!isUnavailableShortMode) setProcessingMode(mode.value); }}
                            className={`w-full p-3 pr-11 rounded-xl text-left transition-all flex items-center gap-3 ${isUnavailableShortMode ? 'bg-muted/30 border-2 border-transparent opacity-50 cursor-not-allowed' : processingMode === mode.value ? 'bg-indigo-500/10 border-2 border-indigo-500/50 dark:bg-indigo-500/20' : 'bg-muted/50 border-2 border-transparent hover:bg-muted hover:border-border'}`}
                          >
                            <span className="text-xl shrink-0">{mode.icon}</span>
                            <div className="min-w-0">
                              <p className={`font-medium text-sm ${processingMode === mode.value && !isUnavailableShortMode ? 'text-indigo-600 dark:text-indigo-400' : ''}`}>{mode.label}</p>
                              <p className="text-xs text-muted-foreground leading-relaxed">{isUnavailableShortMode ? `Requiere un video de al menos ${SHORT_MIN_DURATION_SECONDS}s` : mode.desc}</p>
                            </div>
                          </button>
                          <ProcessingHelpPopover topic={mode.value} className="absolute right-2 top-2 z-10 bg-background/70 backdrop-blur-sm" />
                        </div>
                      );
                    })}
                  </div>
                </div>

                {processingMode === 'short_auto' && (
                  <div className="space-y-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <Label className="text-sm font-medium">2. Duración del clip</Label>
                        <p className="text-[11px] text-muted-foreground mt-0.5">También influye en cómo EleVideo decide el cierre.</p>
                      </div>
                      {shortAutoDurationMode === 'auto' && (
                        <Badge className="bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300">Recomendado</Badge>
                      )}
                    </div>

                    <div className="grid gap-2">
                      {smartClipDurationModes.map((mode) => {
                        const active = shortAutoDurationMode === mode.value;
                        return (
                          <button
                            key={mode.value}
                            type="button"
                            onClick={() => setShortAutoDurationMode(mode.value)}
                            data-testid={`short-duration-mode-${mode.value}`}
                            className={`w-full rounded-lg border p-3 text-left transition-all ${active ? 'border-amber-500/60 bg-amber-500/10 shadow-sm' : 'border-border/70 bg-background/50 hover:border-amber-500/30 hover:bg-amber-500/5'}`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className={`text-sm font-medium ${active ? 'text-amber-700 dark:text-amber-300' : ''}`}>{mode.label}</span>
                              {mode.recommended && <span className="text-[10px] font-medium text-amber-600 dark:text-amber-400">Recomendado</span>}
                            </div>
                            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{mode.desc}</p>
                          </button>
                        );
                      })}
                    </div>

                    {shortAutoDurationMode === 'auto' ? (
                      <div className="rounded-lg border border-amber-500/20 bg-background/40 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
                        Prioriza clips de <span className="font-medium text-foreground">30–60 s</span>, pero puede extenderse hasta <span className="font-medium text-foreground">{formatDuration(shortAutoMaxDuration)}</span> si el contenido necesita más tiempo para cerrar de forma natural.
                      </div>
                    ) : (
                      <div className="space-y-2.5 pt-1">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">{shortAutoDurationMode === 'approximate' ? 'Duración objetivo' : 'Duración exacta'}</span>
                          <span className="px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 text-sm font-bold">{shortAutoDuration}s</span>
                        </div>
                        <Slider value={[shortAutoDuration]} onValueChange={([v]) => setShortAutoDuration(v)} min={SHORT_MIN_DURATION_SECONDS} max={shortAutoMaxDuration} step={1} className="py-1" data-testid="short-duration-slider" />
                        <div className="flex justify-between text-[10px] text-muted-foreground"><span>{SHORT_MIN_DURATION_SECONDS}s</span><span>{formatDuration(shortAutoMaxDuration)}</span></div>
                        {shortAutoDurationMode === 'approximate' && (
                          <p className="text-[11px] leading-relaxed text-muted-foreground">EleVideo puede mover el final unos segundos antes o después para favorecer silencios, cambios de escena o una caída natural de actividad.</p>
                        )}
                        {hasVideoDuration && videoDurationSeconds < selectedPlatformMaxDuration && (
                          <p className="text-[10px] text-center text-muted-foreground">Máximo ajustado a la duración del video: {formatDuration(videoDurationSeconds)}</p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {processingMode === 'short_manual' && (
                  <div className="space-y-3 p-4 rounded-xl bg-sky-500/10 border border-sky-500/20">
                    <div className="flex items-center gap-2 text-sky-600 dark:text-sky-400">
                      <Scissors className="h-4 w-4" />
                      <span className="text-sm font-medium">2. Configurar corte</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Inicio (seg)</Label>
                        <Input type="number" value={shortStartTime} onChange={(e) => handleShortStartTimeChange(e.target.value)} min={0} max={maxManualStartTime} step={1} className="h-9 text-center" data-testid="short-start-time-input" />
                        {hasVideoDuration && <p className="text-[10px] text-center text-muted-foreground">Máx. inicio: {formatDuration(maxManualStartTime)}</p>}
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Duración</Label>
                        <div className="h-9 px-3 rounded-md bg-muted flex items-center justify-center"><span className="font-medium text-sm">{shortDuration}s</span></div>
                        <p className="text-[10px] text-center text-muted-foreground">Máx. disponible: {formatDuration(shortManualMaxDuration)}</p>
                      </div>
                    </div>
                    <Slider value={[shortDuration]} onValueChange={([v]) => setShortDuration(v)} min={SHORT_MIN_DURATION_SECONDS} max={shortManualMaxDuration} step={1} data-testid="short-manual-duration-slider" />
                    <div className="flex justify-between text-[10px] text-muted-foreground"><span>Mín. {SHORT_MIN_DURATION_SECONDS}s</span><span>Máx. {formatDuration(shortManualMaxDuration)}</span></div>
                    <div className="text-center text-xs text-muted-foreground">Resultado: {formatDuration(shortStartTime)} → {formatDuration(shortStartTime + shortDuration)}</div>
                  </div>
                )}

                <div className="space-y-2.5">
                  <Label className="text-sm font-medium">{processingMode === 'vertical' ? '2' : '3'}. Plataforma</Label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { value: 'tiktok', label: 'TikTok', icon: TikTokIcon, activeColor: 'from-[#ff0050] to-[#00f2ea]' },
                      { value: 'instagram', label: 'Reels', icon: InstagramIcon, activeColor: 'from-[#833ab4] via-[#fd1d1d] to-[#fcb045]' },
                      { value: 'youtube_shorts', label: 'Shorts', icon: YouTubeIcon, activeColor: 'from-[#ff0000] to-[#cc0000]' },
                    ].map((p) => (
                      <button key={p.value} type="button" onClick={() => setPlatform(p.value)} className={`p-3 rounded-xl text-center transition-all flex flex-col items-center gap-1.5 ${platform === p.value ? `bg-gradient-to-br ${p.activeColor} shadow-lg text-white` : 'bg-muted/50 border border-border hover:bg-muted text-muted-foreground hover:text-foreground'}`}>
                        <p.icon className="h-5 w-5" />
                        <p className="font-medium text-xs">{p.label}</p>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <Label className="text-sm font-medium">{processingMode === 'vertical' ? '3' : '4'}. Acabado</Label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-2 rounded-xl border border-border/60 bg-muted/20 p-3">
                      <div className="flex items-center gap-1">
                        <Label className="text-xs font-medium">Calidad</Label>
                        <ProcessingHelpPopover topic="quality" />
                      </div>
                      <Select value={quality} onValueChange={setQuality}>
                        <SelectTrigger className="h-9 text-sm" data-testid="quality-select"><SelectValue /></SelectTrigger>
                        <SelectContent>{qualityOptions.map((opt) => <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>)}</SelectContent>
                      </Select>
                      <p className="text-[10px] leading-relaxed text-muted-foreground">{qualityOptions.find((opt) => opt.value === quality)?.desc}</p>
                    </div>
                    <div className="space-y-2 rounded-xl border border-border/60 bg-muted/20 p-3">
                      <div className="flex items-center gap-1">
                        <Label className="text-xs font-medium">Encuadre</Label>
                        <ProcessingHelpPopover topic="backgrounds" />
                      </div>
                      <Select value={backgroundMode} onValueChange={setBackgroundMode}>
                        <SelectTrigger className="h-9 text-sm" data-testid="background-mode-select"><SelectValue /></SelectTrigger>
                        <SelectContent>{backgroundModeOptions.map((opt) => <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>)}</SelectContent>
                      </Select>
                      <p className="text-[10px] leading-relaxed text-muted-foreground">{backgroundModeOptions.find((opt) => opt.value === backgroundMode)?.desc}</p>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between rounded-xl bg-muted/50 p-3 transition-all hover:bg-muted">
                  <div className="flex items-center gap-2">
                    <Settings2 className="h-4 w-4 text-muted-foreground" />
                    <Label htmlFor="advanced-options" className="cursor-pointer text-sm">Opciones avanzadas</Label>
                  </div>
                  <Switch id="advanced-options" checked={showAdvanced} onCheckedChange={setShowAdvanced} data-testid="advanced-options-toggle" />
                </div>

                {showAdvanced && (
                  <AdvancedProcessingOptions
                    backgroundMode={backgroundMode}
                    onChange={setAdvancedOptions}
                  />
                )}

                <Button variant="gradient" className="h-12 w-full rounded-xl text-base font-semibold" onClick={handleProcess} disabled={processMutation.isPending || ((processingMode === 'short_auto' || processingMode === 'short_manual') && shortModesDisabled)} data-testid="process-video-button">
                  {processMutation.isPending ? <Loader2 className="mr-2 h-5 w-5 animate-spin" /> : <Sparkles className="mr-2 h-5 w-5" />}
                  Convertir a vertical
                </Button>
                <p className="text-center text-[10px] text-muted-foreground">El procesamiento puede tardar unos minutos</p>
              </CardContent>
            </Card>
          </aside>

          <section ref={resultsSectionRef} className="order-2 min-w-0 lg:col-span-2 lg:col-start-1 lg:row-start-2">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-5 sm:space-y-6">
              <TabsList className="w-full grid grid-cols-2 h-12 p-1 bg-muted/50">
                <TabsTrigger value="renditions" className="data-[state=active]:bg-background min-w-0 px-2 sm:px-3" data-testid="renditions-tab">
                  <Smartphone className="mr-1.5 sm:mr-2 h-4 w-4 shrink-0" />
                  <span className="hidden sm:inline truncate">Videos procesados ({renditions.length})</span>
                  <span className="sm:hidden truncate">Resultados ({renditions.length})</span>
                </TabsTrigger>
                <TabsTrigger value="jobs" className="data-[state=active]:bg-background min-w-0 px-2 sm:px-3" data-testid="jobs-tab">
                  <Clock className="mr-1.5 sm:mr-2 h-4 w-4 shrink-0" />
                  <span className="truncate">Procesos{activeJobs.length > 0 ? ` · ${activeJobs.length} activo${activeJobs.length === 1 ? '' : 's'}` : ''}</span>
                </TabsTrigger>
              </TabsList>

              <TabsContent value="renditions" className="space-y-4">
                {renditionsLoading ? (
                  <div className="grid gap-4 xl:grid-cols-2">
                    {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-[220px] rounded-2xl" />)}
                  </div>
                ) : renditions.length === 0 ? (
                  <Card className="text-center py-12 border-dashed border-2">
                    <CardContent className="space-y-4">
                      <div className="w-16 h-16 mx-auto rounded-full bg-purple-500/10 flex items-center justify-center">
                        <Smartphone className="h-8 w-8 text-purple-500" />
                      </div>
                      <div>
                        <h3 className="font-outfit font-semibold text-lg">No hay videos procesados</h3>
                        <p className="text-muted-foreground text-sm">Configura el procesamiento de arriba y genera tu primer resultado.</p>
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="grid gap-4 xl:grid-cols-2">
                    {renditions.map((rendition, index) => {
                      const platformBadge = platformBadgeStyles[rendition.platform] ?? { label: rendition.platform || 'Plataforma', className: 'bg-muted text-foreground border-border' };
                      const modeLabel = processingModeLabels[rendition.processingMode] ?? rendition.processingMode ?? 'Video procesado';
                      const qualityLabel = qualityLabels[rendition.quality] ?? rendition.quality ?? 'Normal';
                      const bgLabel = backgroundLabels[rendition.backgroundMode] ?? rendition.backgroundMode ?? 'Encuadre';
                      const PlatformIcon = getPlatformIcon(rendition.platform);
                      const hasSegment = rendition.segmentDuration !== null && rendition.segmentDuration !== undefined;

                      return (
                        <Card key={rendition.id} className="overflow-hidden border-border/60 bg-card/80 transition-all duration-300 hover:border-indigo-500/25 hover:shadow-lg">
                          <div className="grid grid-cols-[112px_minmax(0,1fr)] sm:grid-cols-[140px_minmax(0,1fr)]">
                            <button
                              type="button"
                              onClick={() => openRenditionPreview(rendition)}
                              className="group/preview relative aspect-[9/16] w-full overflow-hidden bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-inset"
                              aria-label={`Ver ${modeLabel}`}
                            >
                              {rendition.thumbnailUrl ? (
                                <img src={rendition.thumbnailUrl} alt={`Vista previa de ${modeLabel}`} className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover/preview:scale-[1.03]" />
                              ) : rendition.previewUrl ? (
                                <video src={rendition.previewUrl} muted playsInline preload="metadata" className="absolute inset-0 h-full w-full object-cover" />
                              ) : (
                                <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-slate-800 to-black">
                                  <Film className="h-9 w-9 text-white/25" />
                                </div>
                              )}
                              <div className="absolute inset-0 bg-gradient-to-t from-black/45 via-transparent to-black/10" />
                              <div className={`absolute left-2 top-2 rounded-full p-1.5 shadow-sm ${platformBadge.className}`} title={platformBadge.label}>
                                <PlatformIcon className="h-3.5 w-3.5 text-current" />
                              </div>
                              <div className="absolute inset-0 flex items-center justify-center">
                                <div className="flex h-11 w-11 items-center justify-center rounded-full bg-white/95 shadow-lg transition-transform group-hover/preview:scale-110">
                                  <Play className="h-4.5 w-4.5 ml-0.5 text-black" />
                                </div>
                              </div>
                            </button>

                            <CardContent className="min-w-0 p-3.5 sm:p-4 flex flex-col gap-3">
                              <div className="space-y-1.5">
                                <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                                  <span className="font-medium text-foreground/80">{platformBadge.label}</span>
                                  {index === 0 && <Badge variant="secondary" className="h-5 px-1.5 text-[9px]">Más reciente</Badge>}
                                </div>
                                <h3 className="font-outfit text-base font-semibold leading-tight">{modeLabel}</h3>
                                {rendition.createdAt && <p className="text-[10px] text-muted-foreground">{timeAgo(rendition.createdAt)}</p>}
                                {hasSegment ? (
                                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                                    <Scissors className="h-3.5 w-3.5" />
                                    <span>{formatDuration(rendition.segmentStart)} → {formatDuration(Number(rendition.segmentStart || 0) + Number(rendition.segmentDuration || 0))}</span>
                                    <span className="text-foreground/40">·</span>
                                    <span>{formatDuration(rendition.segmentDuration)}</span>
                                  </div>
                                ) : (
                                  <p className="text-xs text-muted-foreground">Video completo en formato vertical</p>
                                )}
                              </div>

                              <div className="flex flex-wrap gap-1.5">
                                <Badge variant="outline" className="font-normal text-[10px] sm:text-[11px]">{qualityLabel}</Badge>
                                <Badge variant="outline" className="font-normal text-[10px] sm:text-[11px]">{bgLabel}</Badge>
                              </div>

                              <div className="mt-auto grid grid-cols-[1fr_auto_auto] gap-2 pt-1">
                                <Button size="sm" className="min-w-0" onClick={() => openRenditionPreview(rendition)}>
                                  <Eye className="h-3.5 w-3.5 mr-1.5" />Ver resultado
                                </Button>
                                {rendition.outputUrl && (
                                  <Button asChild size="sm" variant="secondary" title="Descargar">
                                    <a href={rendition.outputUrl} download aria-label="Descargar video procesado"><Download className="h-3.5 w-3.5" /></a>
                                  </Button>
                                )}
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="text-destructive hover:text-destructive"
                                  title="Eliminar"
                                  aria-label="Eliminar video procesado"
                                  onClick={() => { setSelectedRendition(rendition); setIsDeleteRenditionOpen(true); }}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </div>
                            </CardContent>
                          </div>
                        </Card>
                      );
                    })}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="jobs" className="space-y-4">
                {jobsLoading ? (
                  <div className="space-y-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
                ) : jobs.length === 0 ? (
                  <Card className="text-center py-12 border-dashed border-2">
                    <CardContent className="space-y-4">
                      <div className="w-16 h-16 mx-auto rounded-full bg-blue-500/10 flex items-center justify-center"><Clock className="h-8 w-8 text-blue-500" /></div>
                      <div><h3 className="font-outfit font-semibold text-lg">No hay procesos</h3><p className="text-muted-foreground text-sm">Los procesos aparecerán aquí cuando conviertas un video</p></div>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="space-y-3">
                    {jobs.map((job) => {
                      const normalizedStatus = job.status?.toLowerCase();
                      const status = jobStatusConfig[normalizedStatus] || jobStatusConfig.pending;
                      const StatusIcon = status.icon;
                      const progressValue = clampProgress(job.progress);
                      const remainingValue = Math.max(0, 100 - progressValue);
                      const phaseLabel = jobPhaseLabels[job.phase] || (normalizedStatus === 'pending' ? 'Esperando turno' : 'Procesando video');
                      const modeLabel = processingModeLabels[job.processingMode] ?? job.processingMode;
                      return (
                        <Card key={job.id || job.jobId} className="border-border/50" data-testid={`job-${job.id || job.jobId}`}>
                          <CardContent className="p-4">
                            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                              <div className="flex items-center gap-3 sm:gap-4 min-w-0">
                                <div className={`p-2 rounded-lg shrink-0 ${status.className}`}><StatusIcon className={`h-5 w-5 ${normalizedStatus === 'processing' ? 'animate-spin' : ''}`} /></div>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2 flex-wrap"><Badge className={`${status.className} border font-medium`}>{status.label}</Badge><span className="text-sm font-medium">{modeLabel}</span></div>
                                  <p className="text-xs text-muted-foreground mt-1">Proceso {(job.id || job.jobId).slice(0, 8)}...</p>
                                </div>
                              </div>
                              {isActiveJob(job) && (
                                <Button variant="outline" size="sm" onClick={() => cancelJobMutation.mutate(job.id || job.jobId)} disabled={cancelJobMutation.isPending} className="text-destructive hover:text-destructive w-full sm:w-auto shrink-0">
                                  <XCircle className="mr-2 h-4 w-4" />Cancelar
                                </Button>
                              )}
                            </div>
                            {normalizedStatus === 'processing' && (
                              <div className="mt-4 space-y-2.5">
                                <div className="flex items-end justify-between gap-4">
                                  <div className="min-w-0">
                                    <p className="text-sm font-medium truncate">{phaseLabel}</p>
                                    <p className="text-[11px] text-muted-foreground">{remainingValue}% restante</p>
                                  </div>
                                  <span className="font-outfit text-lg font-semibold tabular-nums">{progressValue}%</span>
                                </div>
                                <Progress value={progressValue} className="h-2.5" aria-label={`Progreso ${progressValue}%`} />
                              </div>
                            )}
                            {normalizedStatus === 'failed' && (
                              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm dark:border-red-900 dark:bg-red-950/40">
                                <p className="font-medium text-red-800 dark:text-red-200">
                                  {job.errorDetail || job.errorMessage || job.message || 'No fue posible completar este procesamiento.'}
                                </p>
                                <p className="mt-1 text-xs text-red-700 dark:text-red-300">
                                  Revisa la configuración y vuelve a iniciar la conversión.
                                </p>
                              </div>
                            )}
                          </CardContent>
                        </Card>
                      );
                    })}
                    {jobsTotal > JOBS_VISIBLE_LIMIT && (
                      <p className="text-center text-xs text-muted-foreground pt-1">Mostrando los {JOBS_VISIBLE_LIMIT} procesos más recientes de {jobsTotal}.</p>
                    )}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </section>
        </div>

        <VideoPreviewModal isOpen={isPreviewOpen} onClose={() => { setIsPreviewOpen(false); setPreviewRendition(null); }} video={previewVideo} rendition={previewRendition} />

        <AlertDialog open={isDeleteRenditionOpen} onOpenChange={setIsDeleteRenditionOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>¿Eliminar video procesado?</AlertDialogTitle>
              <AlertDialogDescription>Esta acción no se puede deshacer.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction onClick={() => deleteRenditionMutation.mutate(selectedRendition?.id)} className="bg-destructive hover:bg-destructive/90">
                {deleteRenditionMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Eliminar
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </Layout>
  );
}
