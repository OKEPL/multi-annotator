import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { RefObject, Dispatch, SetStateAction, WheelEvent } from 'react';
import paper from 'paper';

import * as CONFIG from './annotator.config';

import { Dataset, Category } from '../common/types';
import * as AnnotatorApi from './annotator.api';
import useGlobalContext from '../common/hooks/useGlobalContext';
import { addProcess, removeProcess } from '../common/utils/globalActions';

// interfaces
type Maybe<T> = T | null;

interface UserChoicesState {
    annotateMode: [boolean, Dispatch<SetStateAction<boolean>>];
    segmentMode: [boolean, Dispatch<SetStateAction<boolean>>];
    toolState: [Maybe<CONFIG.TOOL>, (name: CONFIG.TOOL) => void];
}
interface CanvasState {
    canvasRef: RefObject<HTMLCanvasElement>;
    imageData: {
        scale: number;
        data: Maybe<ImageData>;
        rasterSize: Maybe<RasterSize>;
    };
    centerImageAction: () => void;
    onWheelAction: (e: WheelEvent<HTMLDivElement>) => void;
}
interface RasterSize {
    width: number;
    height: number;
}

// hooks

// All user decisions
export const useUserChoices = (): UserChoicesState => {
    const annotateMode = useState<boolean>(true);
    const segmentMode = useState<boolean>(true);

    const [tool, setTool] = useState<Maybe<CONFIG.TOOL>>(CONFIG.TOOL.SELECT);
    const toggleTool = (name: CONFIG.TOOL) => {
        setTool(oldState => (oldState === name ? null : name));
    };

    return {
        annotateMode,
        segmentMode,
        toolState: [tool, toggleTool],
    };
};

// Get all related data
export const useData = (imageId: number) => {
    const [, dispatch] = useGlobalContext();

    // datasetdata
    const [dataset, setDataset] = useState<Maybe<Dataset>>(null);
    const [categories, setCategories] = useState<Array<Category>>([]);

    // image data
    const [metadata, setMetadata] = useState<Maybe<{}>>(null);
    const [filename, setFilename] = useState<string>('');
    const [next, setNext] = useState<Maybe<number>>(null);
    const [previous, setPrevious] = useState<Maybe<number>>(null);
    const [categoriesIds, setCategoriesIds] = useState<Array<number>>([]);
    const [annotating, setAnnotating] = useState<[]>([]);

    // others
    const [preferences, setPreferences] = useState<{}>({}); // TODO adjust type

    useEffect(() => {
        const process = 'Loading annotation data';

        const update = async () => {
            const data = await AnnotatorApi.getData(imageId);
            setDataset(data.dataset);
            setCategories(data.categories);
            setMetadata(data.image.metadata || {});
            setFilename(data.image.file_name);
            setNext(data.image.next !== undefined ? data.image.next : null);
            setPrevious(data.image.previous || null);
            setCategoriesIds(data.image.category_ids || []);
            setAnnotating(data.image.annotating || []);

            setPreferences(data.preferences || {});

            setDataset(data.dataset);
        };

        try {
            addProcess(dispatch, process);
            update();
        } catch (error) {
            // TODO display toast
        } finally {
            removeProcess(dispatch, process);
        }
    }, [imageId, dispatch]);

    return {
        dataset,
        categories,
        metadata,
        filename,
        next,
        previous,
        categoriesIds,
        annotating,
        preferences,
    };
};

// Further operations over Image Categories
export const useCategoryData = (categories: Category[]) => {
    const [activeId, _setActiveId] = useState<Maybe<number>>(null);
    const [enableIds, _setEnableIds] = useState<number[]>([]);
    const [expandIds, _setExpandIds] = useState<number[]>([]);

    const [searchText, setSearchText] = useState<string>('');

    const filteredList: Array<Category> = useMemo(() => {
        // Rendered items in right Panel (after applying search filter)
        const search = searchText.toLowerCase();
        if (searchText.length === 0) {
            return categories;
        }
        return categories.filter(category =>
            category.name.toLowerCase().includes(search),
        );
    }, [categories, searchText]);

    const setActiveId = (id: number) => {
        _setActiveId(prev => (id === prev ? null : id));
    };

    const setEnableId = (id: number) => {
        _setEnableIds(prevArr => {
            const arr = [...prevArr];
            const idx = prevArr.indexOf(id);
            if (idx > -1) arr.splice(idx, 1);
            else arr.push(id);
            return arr;
        });
        // collapse expanded row in case category is disabled
        const idx = expandIds.indexOf(id);
        if (idx > -1) setExpandId(id);
    };

    const setExpandId = (id: number) => {
        if (enableIds.indexOf(id) === -1) return;

        _setExpandIds(prevArr => {
            const arr = [...prevArr];
            const idx = prevArr.indexOf(id);
            if (idx > -1) arr.splice(idx, 1);
            else arr.push(id);
            return arr;
        });
    };

    return {
        searchText,
        activeId,
        enableIds,
        expandIds,
        filteredList,
        setSearchText,
        setActiveId,
        setEnableId,
        setExpandId,
    };
};

export const useAnnotationData = () => {
    const add = async (imageId: number, id: number) => {
        await AnnotatorApi.createAnnotation(imageId, id);
    };
    const edit = async (id: number) => {
        // TODO
    };
    const remove = async (annotationId: number) => {
        await AnnotatorApi.deleteAnnotation(annotationId);
    };

    return {
        add,
        edit,
        remove,
    };
};

// Initialize Paper.js and Canvas with image
export const useCanvas = (imageUrl: string): CanvasState => {
    const paperRef = useRef<Maybe<paper.PaperScope>>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const rasterRef = useRef<Maybe<paper.Raster>>(null);

    const [imgScale, setImgScale] = useState<number>(0); // TODO
    const [imgData, setImgData] = useState<Maybe<ImageData>>(null); // TODO
    const [rasterSize, setRasterSize] = useState<Maybe<RasterSize>>(null);

    const centerImageAction = useCallback(() => {
        if (!paperRef.current || !canvasRef.current || !rasterRef.current) {
            return;
        }

        const parentX = rasterRef.current.width || 0;
        const parentY = rasterRef.current.height || 0;

        paperRef.current.view.zoom = Math.min(
            (canvasRef.current.width / parentX) * 0.95,
            (canvasRef.current.height / parentY) * 0.8,
        );

        setImgScale(1 / paperRef.current.view.zoom);
        paperRef.current.view.center = new paper.Point(0, 0);
    }, [canvasRef, rasterRef]);

    const onWheelAction = useCallback((e: WheelEvent<HTMLDivElement>) => {
        if (!paperRef.current || !paperRef.current.view) return;

        const view = paperRef.current.view;

        if (!view.center) return;

        const centerPt = view.center;

        if (e.altKey) {
            // pan up and down
            const delta = new paper.Point(0, CONFIG.PAN_FACTOR * e.deltaY);
            const newCenterP = centerPt.add(delta);
            paperRef.current.view.center = newCenterP;
        } else if (e.shiftKey) {
            // pan left and right
            const delta = new paper.Point(CONFIG.PAN_FACTOR * e.deltaY, 0);
            const newCenterP = centerPt.add(delta);
            paperRef.current.view.center = newCenterP;
        } else {
            // changeZoom
            const viewPosition = view.viewToProject(
                new paper.Point(e.nativeEvent.offsetX, e.nativeEvent.offsetY),
            );

            const oldZoom = view.zoom || 0;
            const newZoom =
                e.deltaY < 0
                    ? oldZoom * CONFIG.ZOOM_FACTOR
                    : oldZoom / CONFIG.ZOOM_FACTOR;
            const beta = oldZoom / newZoom;
            const pc = viewPosition.subtract(centerPt);
            const newOffset = viewPosition
                .subtract(pc.multiply(beta))
                .subtract(centerPt);

            if (newZoom < CONFIG.ZOOM_MAX && newZoom > CONFIG.ZOOM_MIN) {
                setImgScale(1 / newZoom);
                paperRef.current.view.zoom = newZoom;
                paperRef.current.view.center = view.center.add(newOffset);
            }
        }
    }, []);

    // init Canvas
    useEffect(() => {
        if (canvasRef.current != null && paperRef.current == null) {
            console.log('Canvas: Init');

            // in order to prevent forest fires (remove scrollbar when page is active)
            document.body.style.overflow = 'hidden';

            // init Paper
            paperRef.current = new paper.PaperScope();
            paperRef.current.setup(canvasRef.current);
            paperRef.current.view.viewSize = new paper.Size(
                paperRef.current.view.size.width || 0,
                window.innerHeight,
            );
            paperRef.current.activate();

            // init Raster
            rasterRef.current = new paper.Raster(imageUrl);
            rasterRef.current.onLoad = () => {
                if (rasterRef.current === null) return;

                rasterRef.current.sendToBack();
                centerImageAction();

                const width = rasterRef.current.width || 0;
                const height = rasterRef.current.height || 0;

                // collect some fancy data for magicWand tool
                const tempCtx = document
                    .createElement('canvas')
                    .getContext('2d');
                if (tempCtx != null && rasterRef.current.image != null) {
                    tempCtx.canvas.width = width;
                    tempCtx.canvas.height = height;
                    tempCtx.drawImage(rasterRef.current.image, 0, 0);
                    const data = tempCtx.getImageData(0, 0, width, height);
                    setImgData(data); // pass imgData for magicWand tool
                }

                // pass raster to update title
                setRasterSize({ width, height });
            };
        }

        return () => {
            console.log('Canvas: Clean');
            document.body.style.overflow = 'visible';
        };
    }, [canvasRef, centerImageAction, imageUrl]);

    return {
        canvasRef,
        imageData: {
            scale: imgScale,
            data: imgData,
            rasterSize,
        },
        centerImageAction,
        onWheelAction,
    };
};

// Various actions to repaint specific objects from Paper.js context
export const usePainter = (
    rasterSize: Maybe<RasterSize>,
    leftTitle: string,
) => {
    const leftTitleRef = useRef<Maybe<paper.PointText>>(null);
    const rightTitleRef = useRef<Maybe<paper.PointText>>(null);

    // init left and right title
    useEffect(() => {
        if (rasterSize != null) {
            const { width, height } = rasterSize;

            const fontSize = width * CONFIG.TITLE_FONT_SCALE;
            const positionTopLeft = new paper.Point(
                -width / 2,
                -height / 2 - fontSize * CONFIG.TITLE_HEIGHT_SCALE,
            );
            const positionTopRight = new paper.Point(
                width / 2,
                -height / 2 - fontSize * CONFIG.TITLE_HEIGHT_SCALE,
            );

            leftTitleRef.current = new paper.PointText(positionTopLeft);
            leftTitleRef.current.fontSize = fontSize;
            leftTitleRef.current.fillColor = new paper.Color('white');

            rightTitleRef.current = new paper.PointText(positionTopRight);
            rightTitleRef.current.justification = 'right';
            rightTitleRef.current.fontSize = fontSize;
            rightTitleRef.current.fillColor = new paper.Color('white');
            rightTitleRef.current.content = width + 'x' + height;
        }
    }, [rasterSize]);

    // update right title on incoming data
    useEffect(() => {
        if (leftTitleRef.current != null) {
            leftTitleRef.current.content = leftTitle;

            // this.$nextTick(() => this.showAll());    // TODO
        }
    }, [leftTitleRef, leftTitle]);
};
