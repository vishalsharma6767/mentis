declare module 'expo-sensors' {
  export function isAvailableAsync(): Promise<boolean>;
  export function setUpdateIntervalAsync(intervalMs: number): Promise<void>;
  export interface DeviceMotionSubscription {
    remove: () => void;
  }
  export interface DeviceMotionData {
    rotation?: {
      alpha?: number;
      beta?: number;
      gamma?: number;
    };
    accelerometer?: {
      x: number;
      y: number;
      z: number;
    };
  }
  export function addListener(callback: (data: DeviceMotionData) => void): DeviceMotionSubscription;
}
