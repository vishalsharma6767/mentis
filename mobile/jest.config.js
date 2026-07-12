module.exports = {
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {
      tsconfig: {
        jsx: 'react',
        esModuleInterop: true,
        module: 'commonjs',
        moduleResolution: 'node',
        target: 'es2020',
        strict: true,
        types: ['jest'],
        skipLibCheck: true,
      },
      diagnostics: false,
    }],
  },
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
  testPathIgnorePatterns: ['<rootDir>/__tests__/__mocks__/'],
  testEnvironment: 'node',
  moduleNameMapper: {
    'expo-constants': '<rootDir>/__tests__/__mocks__/expo-constants.js',
    '^react-native$': '<rootDir>/__tests__/__mocks__/react-native.js',
    'expo-modules-core': '<rootDir>/__tests__/__mocks__/expo-modules-core.js',
  },
  globals: {
    __DEV__: true,
  },
};
