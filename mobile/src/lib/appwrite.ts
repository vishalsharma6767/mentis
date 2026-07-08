import { Client, Account, ID } from 'react-native-appwrite';
import Constants from 'expo-constants';

const config = {
  endpoint: Constants.expoConfig?.extra?.appwriteEndpoint ?? 'https://sgp.cloud.appwrite.io/v1',
  projectId: Constants.expoConfig?.extra?.appwriteProjectId ?? '',
};

export const client = new Client()
  .setEndpoint(config.endpoint)
  .setProject(config.projectId);

export const account = new Account(client);
export { ID };
export { config as appwriteConfig };
