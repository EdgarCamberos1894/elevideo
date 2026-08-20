const browserSupportsNotifications = () =>
  typeof window !== 'undefined' && 'Notification' in window;

export const requestNotificationPermission = async () => {
  if (!browserSupportsNotifications()) {
    console.log('This browser does not support notifications');
    return false;
  }

  if (Notification.permission === 'granted') {
    return true;
  }

  if (Notification.permission === 'denied') {
    return false;
  }

  // Browsers should only be prompted as a direct consequence of user intent.
  // Calls from effects/background code simply observe the current permission.
  if (navigator.userActivation && !navigator.userActivation.isActive) {
    return false;
  }

  const permission = await Notification.requestPermission();
  return permission === 'granted';
};

export const showNotification = (title, options = {}) => {
  if (!browserSupportsNotifications() || Notification.permission !== 'granted') {
    return undefined;
  }

  const notification = new Notification(title, {
    icon: '/favicon.ico',
    badge: '/favicon.ico',
    ...options,
  });

  notification.onclick = () => {
    window.focus();
    notification.close();
  };

  // Auto close after 5 seconds
  setTimeout(() => notification.close(), 5000);

  return notification;
};

export const notifyProcessingComplete = (videoTitle, status) => {
  const isSuccess = status?.toLowerCase() === 'completed';

  showNotification(
    isSuccess ? 'Video procesado' : 'Error de procesamiento',
    {
      body: isSuccess
        ? `"${videoTitle}" está listo para descargar`
        : `Hubo un error procesando "${videoTitle}"`,
      tag: 'processing-complete',
      requireInteraction: true,
    }
  );
};
