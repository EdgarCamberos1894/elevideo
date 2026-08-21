import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useTheme } from '@/context/ThemeContext';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Sheet, SheetClose, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  LayoutDashboard,
  User,
  LogOut,
  Moon,
  Sun,
  Menu,
  Film,
  Sparkles,
  Bell,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEffect, useState } from 'react';
import { requestNotificationPermission } from '@/lib/notifications';
import { toast } from 'sonner';

const navItems = [
  { href: '/dashboard', label: 'Proyectos', icon: LayoutDashboard },
];

export function Layout({ children }) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const isNavItemActive = (href) => (
    location.pathname === href || (href === '/dashboard' && location.pathname.startsWith('/projects/'))
  );

  useEffect(() => {
    setNotificationsEnabled(Notification.permission === 'granted');
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleEnableNotifications = async () => {
    const granted = await requestNotificationPermission();
    setNotificationsEnabled(granted);
    if (granted) {
      toast.success('Notificaciones activadas');
    } else {
      toast.error('No se pudieron activar las notificaciones');
    }
  };

  return (
    <div className="min-h-screen dashboard-bg">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-[1920px] items-center justify-between px-4 sm:px-6 lg:px-8 2xl:px-12">
          {/* Logo */}
          <Link to="/dashboard" className="flex items-center gap-3 group">
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-purple-500 rounded-xl blur-lg opacity-50 group-hover:opacity-75 transition-opacity" />
              <div className="relative p-2 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600">
                <Film className="h-5 w-5 text-white" />
              </div>
            </div>
            <div className="flex flex-col">
              <span className="font-outfit text-xl font-bold tracking-tight gradient-text">
                Elevideo
              </span>
              <span className="-mt-1 hidden text-xs text-muted-foreground sm:block">
                Conversión vertical con IA
              </span>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                to={item.href}
                aria-current={isNavItemActive(item.href) ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                  isNavItemActive(item.href)
                    ? 'bg-accent/10 text-accent' 
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            ))}
          </nav>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <TooltipProvider delayDuration={250}>
              <div className="hidden items-center gap-2 sm:flex">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={handleEnableNotifications}
                      className={cn('relative', notificationsEnabled && 'text-accent')}
                      aria-label={notificationsEnabled ? 'Notificaciones activadas' : 'Activar notificaciones'}
                      data-testid="notifications-toggle"
                    >
                      <Bell className="h-5 w-5" />
                      {notificationsEnabled && (
                        <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-green-500" aria-hidden="true" />
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{notificationsEnabled ? 'Notificaciones activadas' : 'Activar notificaciones'}</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={toggleTheme}
                      data-testid="theme-toggle"
                      className="relative overflow-hidden"
                      aria-label={theme === 'light' ? 'Usar tema oscuro' : 'Usar tema claro'}
                    >
                      <div className={cn('transition-transform duration-300', theme === 'dark' ? 'rotate-0' : 'rotate-180')}>
                        {theme === 'light' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5 text-yellow-400" />}
                      </div>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{theme === 'light' ? 'Tema oscuro' : 'Tema claro'}</TooltipContent>
                </Tooltip>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      className="flex items-center gap-2 pl-2 pr-3"
                      aria-label={`Abrir menú de ${user?.firstName || 'usuario'}`}
                      data-testid="user-menu-trigger"
                    >
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-purple-600">
                        <span className="text-sm font-medium text-white">
                          {user?.firstName?.[0]}{user?.lastName?.[0]}
                        </span>
                      </div>
                      <span className="hidden text-sm font-medium sm:block">{user?.firstName}</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <div className="px-3 py-2">
                      <p className="font-medium">{user?.firstName} {user?.lastName}</p>
                      <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
                    </div>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem asChild>
                      <Link to="/profile" className="cursor-pointer" data-testid="profile-link">
                        <User className="mr-2 h-4 w-4" />
                        Mi perfil
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={handleLogout}
                      className="cursor-pointer text-destructive focus:text-destructive"
                      data-testid="logout-button"
                    >
                      <LogOut className="mr-2 h-4 w-4" />
                      Cerrar sesión
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </TooltipProvider>

            {/* Mobile Menu */}
            <Sheet>
              <SheetTrigger asChild className="md:hidden">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Abrir menú principal"
                  title="Abrir menú"
                  data-testid="mobile-menu-trigger"
                >
                  <Menu className="h-5 w-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-80">
                <div className="flex h-full flex-col gap-6 py-6">
                  <SheetClose asChild>
                    <Link to="/dashboard" className="flex items-center gap-3">
                      <div className="rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 p-2">
                        <Film className="h-5 w-5 text-white" />
                      </div>
                      <span className="font-outfit text-xl font-bold gradient-text">Elevideo</span>
                    </Link>
                  </SheetClose>

                  <div className="rounded-xl border border-border/60 bg-muted/35 p-3">
                    <p className="font-medium">{user?.firstName} {user?.lastName}</p>
                    <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
                  </div>

                  <nav className="flex flex-col gap-2" aria-label="Navegación principal">
                    {navItems.map((item) => (
                      <SheetClose asChild key={item.href}>
                        <Link
                          to={item.href}
                          aria-current={isNavItemActive(item.href) ? 'page' : undefined}
                          className={cn(
                            'flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-all',
                            isNavItemActive(item.href)
                              ? 'bg-accent/10 text-accent'
                              : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                          )}
                        >
                          <item.icon className="h-5 w-5" />
                          {item.label}
                        </Link>
                      </SheetClose>
                    ))}
                  </nav>

                  <div className="space-y-2 border-t border-border/60 pt-5">
                    <Button variant="ghost" className="w-full justify-start" onClick={toggleTheme}>
                      {theme === 'light' ? <Moon className="mr-2 h-4 w-4" /> : <Sun className="mr-2 h-4 w-4 text-yellow-400" />}
                      {theme === 'light' ? 'Usar tema oscuro' : 'Usar tema claro'}
                    </Button>
                    <Button variant="ghost" className="w-full justify-start" onClick={handleEnableNotifications}>
                      <Bell className="mr-2 h-4 w-4" />
                      {notificationsEnabled ? 'Notificaciones activadas' : 'Activar notificaciones'}
                    </Button>
                    <SheetClose asChild>
                      <Link to="/profile" className="flex items-center rounded-md px-4 py-2 text-sm font-medium hover:bg-muted" data-testid="profile-link-mobile">
                        <User className="mr-2 h-4 w-4" />
                        Mi perfil
                      </Link>
                    </SheetClose>
                    <SheetClose asChild>
                      <Button variant="ghost" className="w-full justify-start text-destructive hover:text-destructive" onClick={handleLogout}>
                        <LogOut className="mr-2 h-4 w-4" />
                        Cerrar sesión
                      </Button>
                    </SheetClose>
                  </div>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto w-full max-w-[1920px] px-4 py-8 sm:px-6 lg:px-8 lg:py-10 2xl:px-12 2xl:py-12">
        {children}
      </main>
    </div>
  );
}
