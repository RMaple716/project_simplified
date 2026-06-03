declare global {
  interface Window {
    AMap: {
      Map: any;
      Marker: any;
      Polyline: any;
      GeometryUtil: {
        decodePath: (encodedPath: string) => any[];
      };
      ToolBar: any;
      Scale: any;
      Driving: any;
      Walking: any;
      Transit: any;
      Riding: any;
    };
  }
}

export {};
