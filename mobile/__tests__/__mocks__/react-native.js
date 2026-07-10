module.exports = {
  Platform: {
    OS: 'web',
    select: (obj) => obj.default || {},
  },
  StyleSheet: {
    create: (styles) => styles,
  },
  Dimensions: {
    get: () => ({ width: 800, height: 600 }),
  },
};
