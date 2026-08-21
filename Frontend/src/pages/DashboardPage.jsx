import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '@/api/projects';
import { Layout } from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  Plus,
  Folder,
  Film,
  MoreVertical,
  Pencil,
  Trash2,
  Loader2,
  Sparkles,
  ArrowRight,
  FolderOpen,
  Search,
  ChevronLeft,
  ChevronRight,
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

const PROJECTS_PAGE_SIZE = 6;

const SORT_OPTIONS = [
  { value: 'createdAt:DESC', label: 'Más nuevos' },
  { value: 'updatedAt:DESC', label: 'Última edición' },
  { value: 'name:ASC', label: 'Nombre A–Z' },
  { value: 'name:DESC', label: 'Nombre Z–A' },
];

function DashboardMetric({ value, label, detail, icon: Icon, iconClass, iconSurface }) {
  return (
    <div className="min-h-[116px] min-w-0 rounded-xl border border-slate-200 bg-white p-3 shadow-[0_12px_30px_-24px_rgba(15,23,42,0.55)] sm:min-h-[132px] sm:p-4 dark:border-slate-800 dark:bg-card/70">
      <div className={`flex h-8 w-8 items-center justify-center rounded-lg sm:h-9 sm:w-9 ${iconSurface}`}>
        <Icon className={`h-4 w-4 sm:h-[18px] sm:w-[18px] ${iconClass}`} aria-hidden="true" />
      </div>
      <p className="mt-3 font-outfit text-2xl font-semibold leading-none text-slate-950 sm:text-3xl dark:text-foreground">
        {value}
      </p>
      <p className="mt-1.5 truncate text-xs font-medium text-slate-700 sm:text-sm dark:text-slate-200">{label}</p>
      <p className="mt-1 hidden truncate text-xs text-slate-500 sm:block dark:text-slate-400">{detail}</p>
    </div>
  );
}

export function DashboardPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState(null);
  const [projectName, setProjectName] = useState('');
  const [projectDescription, setProjectDescription] = useState('');
  const [page, setPage] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [sortValue, setSortValue] = useState('createdAt:DESC');
  const queryClient = useQueryClient();

  const [sortBy, sortDirection] = sortValue.split(':');

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const { data: projectsData, isLoading, error } = useQuery({
    queryKey: ['projects', page, search, sortValue],
    queryFn: () => projectsApi.getAll({
      page,
      size: PROJECTS_PAGE_SIZE,
      sortBy,
      sortDirection,
      ...(search ? { search } : {}),
    }),
  });

  const { data: summaryData } = useQuery({
    queryKey: ['project-summary'],
    queryFn: projectsApi.getSummary,
    retry: false,
  });

  const refreshDashboard = () => {
    queryClient.invalidateQueries({ queryKey: ['projects'] });
    queryClient.invalidateQueries({ queryKey: ['project-summary'] });
  };

  const createMutation = useMutation({
    mutationFn: projectsApi.create,
    onSuccess: () => {
      refreshDashboard();
      setPage(0);
      setIsCreateOpen(false);
      setProjectName('');
      setProjectDescription('');
      toast.success('¡Proyecto creado exitosamente!');
    },
    onError: (mutationError) => {
      toast.error(mutationError.response?.data?.message || 'Error al crear proyecto');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => projectsApi.update(id, data),
    onSuccess: () => {
      refreshDashboard();
      setIsEditOpen(false);
      setSelectedProject(null);
      toast.success('Proyecto actualizado');
    },
    onError: (mutationError) => {
      toast.error(mutationError.response?.data?.message || 'Error al actualizar');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: projectsApi.delete,
    onSuccess: () => {
      if (projects.length === 1 && page > 0) {
        setPage((current) => Math.max(0, current - 1));
      }
      refreshDashboard();
      setIsDeleteOpen(false);
      setSelectedProject(null);
      toast.success('Proyecto eliminado');
    },
    onError: (mutationError) => {
      toast.error(mutationError.response?.data?.message || 'Error al eliminar');
    },
  });

  const openCreateDialog = () => {
    setProjectName('');
    setProjectDescription('');
    setIsCreateOpen(true);
  };

  const handleCreate = (event) => {
    event.preventDefault();
    createMutation.mutate({ name: projectName, description: projectDescription });
  };

  const handleEdit = (event) => {
    event.preventDefault();
    updateMutation.mutate({
      id: selectedProject.id,
      data: { name: projectName, description: projectDescription },
    });
  };

  const openEditDialog = (project) => {
    setSelectedProject(project);
    setProjectName(project.name);
    setProjectDescription(project.description || '');
    setIsEditOpen(true);
  };

  const openDeleteDialog = (project) => {
    setSelectedProject(project);
    setIsDeleteOpen(true);
  };

  const pageData = projectsData?.data || projectsData || {};
  const projects = pageData.content || [];
  const totalElements = Number(pageData.totalElements ?? projects.length);
  const totalPages = Number(pageData.totalPages ?? (totalElements > 0 ? 1 : 0));
  const hasNext = Boolean(pageData.hasNext ?? page + 1 < totalPages);
  const hasPrevious = Boolean(pageData.hasPrevious ?? page > 0);

  const summary = summaryData?.data || summaryData || {};
  const projectCount = Number(summary.projectCount ?? totalElements);
  const parsedVideoCount = Number(summary.videoCount);
  const parsedConversionCount = Number(summary.conversionCount);
  const videoCount = Number.isFinite(parsedVideoCount) ? parsedVideoCount : null;
  const conversionCount = Number.isFinite(parsedConversionCount) ? parsedConversionCount : null;
  const metrics = [
    {
      value: projectCount,
      label: 'Proyectos',
      detail: 'Colecciones creadas',
      icon: Folder,
      iconClass: 'text-blue-600 dark:text-blue-300',
      iconSurface: 'bg-blue-50 dark:bg-blue-500/15',
    },
    ...(videoCount !== null ? [{
      value: videoCount,
      label: 'Videos',
      detail: 'Archivos cargados',
      icon: Film,
      iconClass: 'text-violet-600 dark:text-violet-300',
      iconSurface: 'bg-violet-50 dark:bg-violet-500/15',
    }] : []),
    ...(conversionCount !== null ? [{
      value: conversionCount,
      label: 'Resultados',
      detail: 'Conversiones listas',
      icon: Sparkles,
      iconClass: 'text-emerald-600 dark:text-emerald-300',
      iconSurface: 'bg-emerald-50 dark:bg-emerald-500/15',
    }] : []),
  ];
  const hasAnyProjects = projectCount > 0 || totalElements > 0;
  const isSearchEmpty = projects.length === 0 && Boolean(search);
  const firstVisible = totalElements === 0 ? 0 : page * PROJECTS_PAGE_SIZE + 1;
  const lastVisible = Math.min(totalElements, (page + 1) * PROJECTS_PAGE_SIZE);

  const renderProjectsSkeleton = () => (
    <div
      className="grid gap-5 sm:gap-6"
      style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 20rem), 1fr))' }}
    >
      {[...Array(PROJECTS_PAGE_SIZE)].map((_, index) => (
        <Card key={index} className="h-[250px] w-full overflow-hidden border-border/60">
          <div className="h-24 bg-gradient-to-br from-muted to-muted/50" />
          <CardHeader>
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="mt-2 h-4 w-1/2" />
          </CardHeader>
        </Card>
      ))}
    </div>
  );

  const renderProjectsGrid = () => (
    <>
      <div
        className="grid gap-5 sm:gap-6"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 20rem), 1fr))' }}
      >
        {projects.map((project, index) => {
          const seed = Number(project.id ?? index);
          return (
            <Card
              key={project.id}
              className="card-3d group relative h-full overflow-hidden border-border/60 bg-card hover:border-indigo-500/40 dark:bg-card/80"
              data-testid={`project-card-${project.id}`}
            >
                <div
                  className="relative h-24 overflow-hidden"
                  style={{
                    background: `linear-gradient(135deg,
                      hsl(${220 + (seed * 30) % 60}, 70%, ${50 + (seed % 3) * 5}%),
                      hsl(${260 + (seed * 30) % 60}, 70%, ${45 + (seed % 3) * 5}%))`,
                  }}
                >
                  <div className="absolute inset-0 bg-black/10" />
                  <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-card to-transparent dark:from-card/95" />
                  <div className="absolute right-3 top-3 z-20">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 bg-black/45 text-white hover:bg-black/65"
                          aria-label={`Acciones de ${project.name}`}
                          title="Acciones del proyecto"
                          data-testid={`project-menu-${project.id}`}
                        >
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openEditDialog(project)}>
                          <Pencil className="mr-2 h-4 w-4" />Editar
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => openDeleteDialog(project)}
                          className="text-destructive focus:text-destructive"
                        >
                          <Trash2 className="mr-2 h-4 w-4" />Eliminar
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  <div className="absolute -bottom-5 left-4">
                    <div className="rounded-xl border border-border/60 bg-card p-3 shadow-lg dark:bg-slate-800">
                      <Folder className="h-6 w-6 text-indigo-500 transition-colors group-hover:text-purple-500" />
                    </div>
                  </div>
                </div>

                <CardHeader className="pt-8">
                  <CardTitle className="flex items-center justify-between font-outfit text-lg text-foreground transition-colors group-hover:text-indigo-500">
                    <Link
                      to={`/projects/${project.id}`}
                      className="truncate after:absolute after:inset-0 focus-visible:rounded-sm"
                    >
                      {project.name}
                    </Link>
                    <ArrowRight className="h-4 w-4 flex-shrink-0 -translate-x-2 opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
                  </CardTitle>
                  {project.description && <CardDescription className="line-clamp-2">{project.description}</CardDescription>}
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
                    <div className="flex items-center gap-1.5">
                      <Film className="h-4 w-4" />
                      <span>{project.videoCount || 0} video{project.videoCount === 1 ? '' : 's'}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="h-4 w-4" />
                      <span>{project.conversionCount || 0} resultado{project.conversionCount === 1 ? '' : 's'}</span>
                    </div>
                  </div>
                </CardContent>
            </Card>
          );
        })}
      </div>

      {totalPages > 1 && (
        <nav className="mt-5 flex flex-col gap-3 border-t border-border/60 pt-4 sm:flex-row sm:items-center sm:justify-between" aria-label="Paginación de proyectos">
          <p className="text-center text-xs text-muted-foreground sm:text-left">
            Mostrando {firstVisible}–{lastVisible} de {totalElements}
          </p>
          <div className="flex items-center justify-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((current) => Math.max(0, current - 1))}
              disabled={!hasPrevious}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />Anterior
            </Button>
            <span className="min-w-[92px] text-center text-xs font-medium text-muted-foreground">
              Página {page + 1} de {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((current) => current + 1)}
              disabled={!hasNext}
            >
              Siguiente<ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </nav>
      )}
    </>
  );

  return (
    <Layout>
      <div className="space-y-6 sm:space-y-8" data-testid="dashboard-page">
        <div className="max-w-2xl space-y-1">
          <h1 className="font-outfit text-3xl font-bold tracking-tight sm:text-4xl">
            Panel de <span className="gradient-text">contenido</span>
          </h1>
          <p className="text-base text-muted-foreground sm:text-lg">
            Consulta el avance de tus proyectos y conversiones.
          </p>
        </div>

        <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
          <DialogContent className="sm:max-w-md">
            <form onSubmit={handleCreate}>
              <DialogHeader>
                <DialogTitle className="font-outfit text-xl">Crear proyecto</DialogTitle>
                <DialogDescription>Los proyectos te ayudan a organizar tus videos</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-6">
                <div className="space-y-2">
                  <Label htmlFor="name">Nombre del proyecto</Label>
                  <Input
                    id="name"
                    value={projectName}
                    onChange={(event) => setProjectName(event.target.value)}
                    placeholder="Ej: Videos de TikTok"
                    className="h-11"
                    data-testid="project-name-input"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">Descripción (opcional)</Label>
                  <Textarea
                    id="description"
                    value={projectDescription}
                    onChange={(event) => setProjectDescription(event.target.value)}
                    placeholder="Describe tu proyecto..."
                    className="resize-none"
                    rows={3}
                    data-testid="project-description-input"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  type="submit"
                  variant="brand"
                  className="w-full"
                  disabled={createMutation.isPending}
                  data-testid="create-project-submit"
                >
                  {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Crear proyecto
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        {hasAnyProjects && (
          <section
            className="grid gap-2.5 sm:gap-4"
            style={{ gridTemplateColumns: `repeat(${Math.max(1, metrics.length)}, minmax(0, 1fr))` }}
            aria-label="Resumen del contenido"
            data-testid="dashboard-metrics"
          >
            {metrics.map((metric) => <DashboardMetric key={metric.label} {...metric} />)}
          </section>
        )}

        {isLoading && !hasAnyProjects ? (
          renderProjectsSkeleton()
        ) : error ? (
          <Card className="border-destructive/50 py-16 text-center">
            <CardContent className="space-y-4">
              <p className="text-destructive">Error al cargar proyectos</p>
              <Button onClick={() => queryClient.invalidateQueries({ queryKey: ['projects'] })}>Reintentar</Button>
            </CardContent>
          </Card>
        ) : !hasAnyProjects ? (
          <div className="relative">
            <div className="empty-state-bg absolute inset-0 rounded-3xl" />
            <Card className="relative border-2 border-dashed bg-transparent py-20 text-center">
              <CardContent className="space-y-6">
                <div className="relative inline-flex">
                  <div className="absolute inset-0 animate-pulse rounded-full bg-gradient-to-r from-blue-500 to-purple-500 opacity-30 blur-xl" />
                  <div className="relative rounded-full border border-purple-500/20 bg-gradient-to-br from-blue-500/10 to-purple-500/10 p-6">
                    <FolderOpen className="h-16 w-16 text-purple-500" />
                  </div>
                </div>
                <div className="space-y-2">
                  <h3 className="font-outfit text-2xl font-semibold">Crea tu primer proyecto</h3>
                  <p className="mx-auto max-w-sm text-muted-foreground">
                    Los proyectos te ayudan a organizar tus videos y generar contenido vertical para redes sociales
                  </p>
                </div>
                <Button
                  size="lg"
                  variant="gradient"
                  onClick={openCreateDialog}
                >
                  <Sparkles className="mr-2 h-5 w-5" />
                  Crear mi primer proyecto
                </Button>
              </CardContent>
            </Card>
          </div>
        ) : (
          <section
            className="relative mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_20px_60px_-42px_rgba(15,23,42,0.42)] ring-1 ring-slate-900/[0.025] dark:border-slate-800 dark:bg-card/55 dark:shadow-sm dark:ring-0"
            aria-labelledby="projects-library-title"
          >
            <div
              className="h-1 w-full bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500"
              aria-hidden="true"
            />

            <div
              className="border-b border-slate-200 bg-white px-4 py-4 dark:border-slate-800 dark:bg-slate-900/35 sm:px-6 sm:py-6"
              data-testid="projects-library-header"
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
                <div className="min-w-0">
                  <h2 id="projects-library-title" className="font-outfit text-xl font-semibold text-slate-950 dark:text-foreground sm:text-2xl">
                    Mis proyectos
                  </h2>
                  <p className="mt-1.5 hidden max-w-2xl text-sm text-slate-600 dark:text-muted-foreground sm:block">
                    Busca, ordena y abre tus proyectos desde un solo lugar.
                  </p>
                </div>
                <div className="flex w-full items-center gap-2 sm:w-auto sm:shrink-0">
                  <span
                    className="w-fit shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                    data-testid="projects-count"
                  >
                    {search
                      ? `${totalElements} resultado${totalElements === 1 ? '' : 's'}`
                      : `${projectCount} proyecto${projectCount === 1 ? '' : 's'}`}
                  </span>
                  <Button
                    variant="gradient"
                    className="h-10 min-w-0 flex-1 px-4 sm:flex-none"
                    onClick={openCreateDialog}
                    data-testid="create-project-button"
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    Nuevo proyecto
                  </Button>
                </div>
              </div>

              <div className="mt-4 sm:mt-5" data-testid="projects-library-filters">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="relative w-full sm:max-w-md">
                    <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-slate-400" />
                    <Input
                      value={searchInput}
                      onChange={(event) => setSearchInput(event.target.value)}
                      placeholder="Buscar proyecto..."
                      className="h-11 border-slate-300 bg-white pl-10 text-slate-900 shadow-sm transition-colors placeholder:text-slate-500 hover:border-slate-400 focus-visible:border-indigo-400 focus-visible:ring-indigo-500/25 dark:border-slate-700 dark:bg-slate-950/80 dark:text-slate-100 dark:placeholder:text-slate-400 dark:hover:border-slate-600"
                      aria-label="Buscar proyecto por nombre o descripción"
                    />
                  </div>

                  <Select
                    value={sortValue}
                    onValueChange={(value) => {
                      setSortValue(value);
                      setPage(0);
                    }}
                  >
                    <SelectTrigger
                      className="h-11 w-full border-slate-300 bg-white text-slate-900 shadow-sm transition-colors hover:border-slate-400 focus:ring-indigo-500/25 dark:border-slate-700 dark:bg-slate-950/80 dark:text-slate-100 dark:hover:border-slate-600 sm:w-[205px]"
                      aria-label="Ordenar proyectos"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SORT_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="mt-3 hidden flex-col gap-2 border-t border-slate-200/80 pt-3 text-xs text-slate-500 dark:border-slate-800 dark:text-muted-foreground sm:flex sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    {search
                      ? `${totalElements} resultado${totalElements === 1 ? '' : 's'} para “${search}”`
                      : 'La búsqueda y el orden se aplican a los proyectos mostrados abajo.'}
                  </span>
                  {search && (
                    <button
                      type="button"
                      className="w-fit font-medium text-indigo-600 transition-colors hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
                      onClick={() => setSearchInput('')}
                    >
                      Limpiar búsqueda
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div
              className="bg-slate-50/75 p-4 dark:bg-background/35 sm:p-6"
              data-testid="projects-library-content"
            >
              {isLoading ? (
                renderProjectsSkeleton()
              ) : isSearchEmpty ? (
                <Card className="border-dashed border-slate-300 bg-white py-14 text-center shadow-sm dark:border-slate-700 dark:bg-card/70">
                  <CardContent className="space-y-4">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                      <Search className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <h3 className="font-outfit text-lg font-semibold">No encontramos ese proyecto</h3>
                      <p className="mt-1 text-sm text-muted-foreground">Prueba con otro nombre o una palabra de la descripción.</p>
                    </div>
                    <Button variant="outline" onClick={() => setSearchInput('')}>Limpiar búsqueda</Button>
                  </CardContent>
                </Card>
              ) : (
                renderProjectsGrid()
              )}
            </div>
          </section>
        )}

        <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
          <DialogContent>
            <form onSubmit={handleEdit}>
              <DialogHeader>
                <DialogTitle className="font-outfit">Editar proyecto</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="edit-name">Nombre</Label>
                  <Input
                    id="edit-name"
                    value={projectName}
                    onChange={(event) => setProjectName(event.target.value)}
                    data-testid="edit-project-name-input"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-description">Descripción</Label>
                  <Textarea
                    id="edit-description"
                    value={projectDescription}
                    onChange={(event) => setProjectDescription(event.target.value)}
                    data-testid="edit-project-description-input"
                    rows={3}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button type="submit" variant="brand" disabled={updateMutation.isPending}>
                  {updateMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Guardar cambios
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        <AlertDialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>¿Eliminar proyecto?</AlertDialogTitle>
              <AlertDialogDescription>
                Esta acción no se puede deshacer. Se eliminarán todos los videos del proyecto.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancelar</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => deleteMutation.mutate(selectedProject?.id)}
                className="bg-destructive hover:bg-destructive/90"
                data-testid="confirm-delete-project"
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
